#!/usr/bin/env python3
"""Generate Structurizr DSL via pystructurizr — IDs in Flows, names in diagram.

* Outbound / Inbound contiennent des **ID**.
* Le script déduplique désormais automatiquement les flux strictement identiques afin d’éviter les doublons dans le DSL.
* Le libellé de la flèche inclut maintenant le champ **Name** du flux, suivi de l’Objet et du Format :  
  `FlowName / Objet (Format)`

Usage :
    python generate_pystructurizr_id_v2.py flows_applications.xlsx --output diagrams

Dépendances :
    pip install git+https://github.com/nielsvanspauwen/pystructurizr.git pandas openpyxl
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Tuple

import pandas as pd
from pystructurizr.dsl import Workspace

# Colonnes requises
REQUIRED_APP = {"ID", "Name", "Application", "Component", "ParentAppID"}
REQUIRED_FLOW = {"ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Status"}


# ---------------------------------------------------------------------------- CLI

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Structurizr workspace from Excel inventory (IDs mode)"
    )
    parser.add_argument("file", type=Path, help="flows_applications.xlsx")
    parser.add_argument("--output", type=Path, default=Path("build"), help="Output directory")
    parser.add_argument(
        "--views", default="system,container", help="Views to generate (comma-separated)"
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------- Excel loading

def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    read_kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")

    apps_df = pd.read_excel(path, sheet_name="Applications", **read_kw)
    flows_df = pd.read_excel(path, sheet_name="Flows", **read_kw)

    # Nettoyage : trim espaces
    for col in ("ID", "ParentAppID"):
        apps_df[col] = apps_df[col].str.strip()

    for col in ("Outbound", "Inbound"):
        flows_df[col] = flows_df[col].str.strip()

    return apps_df, flows_df


# ---------------------------------------------------------------------------- Validation

def validate(apps_df: pd.DataFrame, flows_df: pd.DataFrame) -> None:
    missing_app = REQUIRED_APP - set(apps_df.columns)
    missing_flow = REQUIRED_FLOW - set(flows_df.columns)
    if missing_app:
        raise ValueError(f"Applications sheet missing columns: {', '.join(missing_app)}")
    if missing_flow:
        raise ValueError(f"Flows sheet missing columns: {', '.join(missing_flow)}")

    id_set = set(apps_df["ID"])

    # ParentAppID cohérence
    bad_parent = apps_df[(apps_df["Component"] == "#") & (~apps_df["ParentAppID"].isin(id_set))]
    if not bad_parent.empty:
        rows = ", ".join(map(str, bad_parent.index.tolist()))
        raise ValueError(f"Invalid ParentAppID for rows: {rows}")

    # Outbound / Inbound
    for col in ("Outbound", "Inbound"):
        bad = flows_df[~flows_df[col].isin(id_set)]
        if not bad.empty:
            rows = ", ".join(map(str, bad.index.tolist()))
            raise ValueError(f"{col} references unknown IDs (rows: {rows})")

    # Champs critiques non vides
    for col in ("Protocol", "Objet", "Format"):
        empty = flows_df[flows_df[col] == ""]
        if not empty.empty:
            rows = ", ".join(map(str, empty.index.tolist()))
            raise ValueError(f"Column {col} contains empty cells (rows: {rows})")


# ---------------------------------------------------------------------------- Workspace builder

def build_workspace(apps_df: pd.DataFrame, flows_df: pd.DataFrame, views_spec: str) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")

    elem_by_id = {}
    systems_by_id = {}

    # Software Systems
    for _, row in apps_df[apps_df["Application"] == "#"].iterrows():
        ss = model.SoftwareSystem(row["Name"], row.get("Description", ""))
        ss.tags.append("ApplicationSystem")
        elem_by_id[row["ID"]] = ss
        systems_by_id[row["ID"]] = ss

    # Containers
    for _, row in apps_df[apps_df["Component"] == "#"].iterrows():
        parent_sys = systems_by_id.get(row["ParentAppID"])
        if not parent_sys:
            logging.warning(
                "Skip container %s: parent %s not found", row["ID"], row["ParentAppID"]
            )
            continue
        container = parent_sys.Container(
            row["Name"], row.get("Description", ""), technology=""
        )
        container.tags.append("ApplicationContainer")
        elem_by_id[row["ID"]] = container

    # Relationships (déduplication)
    seen = set()
    for _, flow in flows_df.iterrows():
        src = elem_by_id.get(flow["Outbound"])
        dst = elem_by_id.get(flow["Inbound"])
        if not src or not dst:
            logging.warning("Skip flow: %s -> %s not mapped", flow["Outbound"], flow["Inbound"])
            continue

        key = (flow["Outbound"], flow["Inbound"], flow["Objet"], flow["Protocol"], flow["Format"])
        if key in seen:
            logging.debug("Duplicate flow skipped: %s", key)
            continue
        seen.add(key)

        # Label = Name / Objet (Format)
        label = f"{flow['Name']} / {flow['Objet']} ({flow['Format']})" if flow["Name"] else f"{flow['Objet']} ({flow['Format']})"

        rel = src.uses(dst, label, flow["Protocol"])
        # Conserver le status en propriété si nécessaire


    # Views
    views_set = {v.strip().lower() for v in views_spec.split(',') if v.strip()}
    if "system" in views_set:
        ws.SystemLandscapeView("SystemLandscape", "All systems")
    if "container" in views_set:
        for sys in systems_by_id.values():
            if not sys.elements:
                continue
            ws.ContainerView(sys, f"{sys.name}_Container", f"Containers for {sys.name}")

    # Styles (éléments)
    ws.Styles(
        {"tag": "ApplicationSystem", "shape": "RoundedBox", "background": "#1168bd", "color": "#ffffff"},
        {"tag": "ApplicationContainer", "shape": "Box", "background": "#438dd5", "color": "#ffffff"}
    )

    return ws


# ---------------------------------------------------------------------------- Main

def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level)

    apps_df, flows_df = load_excel(args.file)
    validate(apps_df, flows_df)

    workspace = build_workspace(apps_df, flows_df, args.views)

    args.output.mkdir(parents=True, exist_ok=True)
    dsl_path = args.output / "workspace.dsl"
    dsl_path.write_text(workspace.dump(), encoding="utf-8")
    print("DSL saved →", dsl_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)
