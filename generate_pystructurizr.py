
#!/usr/bin/env python3
"""Generate a Structurizr workspace using **pystructurizr** from an Excel inventory.

Requirements:
  pip install pystructurizr pandas openpyxl
"""

import argparse
import logging
from pathlib import Path
import sys

import pandas as pd
from pystructurizr.dsl import Workspace   # <— main dependency

# --------------------------------------------------------------------------- CLI
def parse_args():
    p = argparse.ArgumentParser(description="Create Structurizr DSL via pystructurizr")
    p.add_argument("file", type=Path, help="flows_applications.xlsx")
    p.add_argument("--output", type=Path, default=Path("build"), help="Output directory")
    p.add_argument("--views", default="system,container", help="Views to generate (comma‑sep)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()

# --------------------------------------------------------------------------- Validation helpers
REQUIRED_APP_COLS = {"ID", "Name", "Application", "Component", "ParentAppID"}
REQUIRED_FLOW_COLS = {"ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Status"}

def validate(apps_df: pd.DataFrame, flows_df: pd.DataFrame):
    missing_app = REQUIRED_APP_COLS - set(apps_df.columns)
    missing_flow = REQUIRED_FLOW_COLS - set(flows_df.columns)
    if missing_app:
        raise ValueError(f"Applications sheet missing: {', '.join(missing_app)}")
    if missing_flow:
        raise ValueError(f"Flows sheet missing: {', '.join(missing_flow)}")

    ids = set(apps_df["ID"])
    names = set(apps_df["Name"])


    bad_parent = apps_df[(apps_df["Component"] == "#") & (~apps_df["ParentAppID"].isin(ids))]


    if not bad_parent.empty:
        raise ValueError("Invalid ParentAppID for rows: " + ", ".join(map(str, bad_parent.index.tolist())))

    for col in ("Outbound", "Inbound"):
        bad = flows_df[~flows_df[col].isin(ids)]
        if not bad.empty:
            raise ValueError(f"{col} references unknown names (rows {', '.join(map(str, bad.index.tolist()))})")

    # Critical empty check
    for col in ("Protocol", "Objet", "Format"):
        empty = flows_df[flows_df[col] == ""]
        if not empty.empty:
            raise ValueError(f"Column {col} contains empty cells (rows {', '.join(map(str, empty.index.tolist()))})")
    print(f"Fichier valide")
# --------------------------------------------------------------------------- Build
def build_workspace(apps_df: pd.DataFrame, flows_df: pd.DataFrame, views_sel):
    ws = Workspace()
    model = ws.Model(name="model")

    # Maps
    sys_by_id = {}
    elem_by_name = {}

    # Software Systems
    for _, row in apps_df[apps_df["Application"] == "#"].iterrows():
        sys = model.SoftwareSystem(row["Name"], row.get("Description", ""))
        sys_by_id[row["ID"]] = sys
        elem_by_name[row["Name"]] = sys
        sys.tags.extend(["ApplicationSystem"])
  
    #   
    for _, row in apps_df[apps_df["Component"] == "#"].iterrows():
        parent_sys = sys_by_id.get(row["ParentAppID"])
        if not parent_sys:
            continue  # safety
        container = parent_sys.Container(row["Name"], row.get("Description", ""), technology="")
        container.tags.extend(["ApplicationContainer"])
        elem_by_name[row["Name"]] = container

    # Relationships
    for _, flow in flows_df.iterrows():
        src = elem_by_name[flow["Outbound"]]
        dst = elem_by_name[flow["Inbound"]]
        desc = f"{flow['Objet']} ({flow['Format']})"
        rel = src.uses(dst, desc, flow["Protocol"])
        # Add status tag if present
        if flow["Status"]:
            if not hasattr(rel, 'tags'):
                rel.tags = []
            rel.tags.append(flow["Status"])
        print("Éléments créés :", elem_by_name.keys())            # IDs effectivement ajoutés
        print("Outbound uniques :", flows_df["Outbound"].unique()[:20])
        print("Inbound  uniques :", flows_df["Inbound"].unique()[:20])

    # ------------ VIEWS -------------
    views_sel = {v.strip().lower() for v in views_sel.split(',')}

    if "system" in views_sel:
        v = ws.SystemLandscapeView("SystemLandscape", "All systems")
        # include * added automatically by pystructurizr; autolayout default ON in dump

    if "container" in views_sel:
        for sys in sys_by_id.values():
            # create container view only for systems having containers
            if not sys.elements:
                continue
            ws.ContainerView(sys, f"{sys.name}_Container", f"Containers for {sys.name}")

    # ------------ STYLES -------------
    ws.Styles(
        {"tag": "ApplicationSystem", "shape": "RoundedBox", "background": "#1168bd", "color": "#ffffff"},
        {"tag": "ApplicationContainer", "shape": "Box", "background": "#438dd5", "color": "#ffffff"},
        {"tag": "Add", "color": "#28a745"},
        {"tag": "Change", "color": "#ff8c00"},
        {"tag": "Keep", "color": "#6c757d"},
    )

    return ws

# --------------------------------------------------------------------------- Main
def main():
    args = parse_args()
    logging.basicConfig(level=args.log_level)
    read_kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")
    apps_df = pd.read_excel(args.file, sheet_name="Applications", **read_kw).fillna("")
    flows_df = pd.read_excel(args.file, sheet_name="Flows", **read_kw).fillna("")

    # nettoyer espaces et casse si besoin
    for col in ("ID", "ParentAppID"):
        apps_df[col] = apps_df[col].str.strip()

    for col in ("Outbound", "Inbound"):
        flows_df[col] = flows_df[col].str.strip()


    validate(apps_df, flows_df)

    ws = build_workspace(apps_df, flows_df, args.views)
    print(f"Workspace OK")
    dsl_text = ws.dump()

    args.output.mkdir(parents=True, exist_ok=True)
    dsl_path = args.output / "workspace.dsl"
    dsl_path.write_text(dsl_text, encoding="utf-8")
    print(f"DSL saved → {dsl_path}")

    print("\nYou can preview quickly with Structurizr‑Lite:")
    print(f" docker run -it --rm -p 8080:8080 -v $(pwd)/{args.output.name}:/usr/local/structurizr structurizr/lite")

    # Summary
    num_systems = len([e for e in ws.models if isinstance(e, type(ws.Model().SoftwareSystem("dummy")) )])  # rough count
    num_rels = sum(len(e.relationships) for e in ws.models for e in e.elements) if ws.models else "?"
    print(f"Summary → Systems: {len(ws.models)} • Relationships: {num_rels}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)
