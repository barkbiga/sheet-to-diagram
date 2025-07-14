#!/usr/bin/env python3
"""Generate Structurizr DSL via pystructurizr — IDs in Flows, names in diagram (v4).

Nouveautés v4
-------------
* Le **Status** est désormais lu depuis l’onglet **Applications** (pas Flows) ;
  il colore l’élément (SoftwareSystem ou Container).
* Palette :
  * **Add**    → vert `#28a745`
  * **Change** → orange `#ff8c00`
  * **Remove** → rouge `#d9534f`
  * **Keep** ou vide → couleur par défaut.
* Les colonnes obligatoires mises à jour : `Applications.Status` devient requise,
  `Flows.Status` n’est plus nécessaire.
* Déduplication des flux identiques et libellé `Name / Objet (Format)` conservés.

Usage :
    python generate_pystructurizr_id_v4.py flows_applications.xlsx --output diagrams

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

REQUIRED_APP = {
    "ID",
    "Name",
    "Application",
    "Component",
    "ParentAppID",
    "Status",  # nouvelle colonne obligatoire
}
REQUIRED_FLOW = {
    "ID",
    "Name",
    "Outbound",
    "Inbound",
    "Objet",
    "Protocol",
    "Format",
}


# ------------------------------------------------ CLI

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


# ------------------------------------------------ Excel loading

def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    read_kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")
    apps = pd.read_excel(path, sheet_name="Applications", **read_kw)
    flows = pd.read_excel(path, sheet_name="Flows", **read_kw)

    for col in ("ID", "ParentAppID"):
        apps[col] = apps[col].str.strip()
    for col in ("Outbound", "Inbound"):
        flows[col] = flows[col].str.strip()

    apps["Status"] = apps["Status"].str.strip().str.lower()

    return apps, flows


# ------------------------------------------------ Validation

def validate(apps: pd.DataFrame, flows: pd.DataFrame):
    if (miss := REQUIRED_APP - set(apps.columns)):
        raise ValueError(f"Applications missing: {', '.join(miss)}")
    if (miss := REQUIRED_FLOW - set(flows.columns)):
        raise ValueError(f"Flows missing: {', '.join(miss)}")

    idset = set(apps["ID"])
    bad_parent = apps[(apps["Component"] == "#") & (~apps["ParentAppID"].isin(idset))]
    if not bad_parent.empty:
        raise ValueError("Invalid ParentAppID rows: " + ", ".join(map(str, bad_parent.index)))

    for col in ("Outbound", "Inbound"):
        missing = flows[~flows[col].isin(idset)]
        if not missing.empty:
            raise ValueError(f"{col} unknown IDs rows: {', '.join(map(str, missing.index))}")

    for col in ("Protocol", "Objet", "Format"):
        empty = flows[flows[col] == ""]
        if not empty.empty:
            raise ValueError(f"Column {col} empty rows: {', '.join(map(str, empty.index))}")


# ------------------------------------------------ Workspace builder

def build_workspace(apps: pd.DataFrame, flows: pd.DataFrame, views_spec: str) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")

    elem_by_id, systems_by_id = {}, {}

    colour_map = {
        "add": "#28a745",
        "change": "#ff8c00",
        "remove": "#d9534f",
        "keep": None,
    }

    # Systems
    for _, row in apps[apps["Application"] == "#"].iterrows():
        sys_elem = model.SoftwareSystem(row["Name"], row.get("Description", ""))
        sys_elem.tags.append("ApplicationSystem")
        status_col = colour_map.get(row["Status"].lower() if row["Status"] else "keep")
        if status_col:
            sys_elem.color = status_col
        elem_by_id[row["ID"]] = sys_elem
        systems_by_id[row["ID"]] = sys_elem

    # Containers
    for _, row in apps[apps["Component"] == "#"].iterrows():
        parent = systems_by_id.get(row["ParentAppID"])
        if not parent:
            logging.warning(
                "Skip container %s: parent %s missing", row["ID"], row["ParentAppID"]
            )
            continue
        container = parent.Container(row["Name"], row.get("Description", ""), technology="")
        container.tags.append("ApplicationContainer")
        status_col = colour_map.get(row["Status"].lower() if row["Status"] else "keep")
        if status_col:
            container.color = status_col
        elem_by_id[row["ID"]] = container

    # Relationships (déduplication)
    seen = set()
    for _, f in flows.iterrows():
        src, dst = elem_by_id.get(f["Outbound"]), elem_by_id.get(f["Inbound"])
        if not src or not dst:
            logging.warning("Skip flow: %s -> %s unmapped", f["Outbound"], f["Inbound"])
            continue

        key = (f["Outbound"], f["Inbound"], f["Objet"], f["Protocol"], f["Format"])
        if key in seen:
            continue
        seen.add(key)

        label = (
            f"{f['Name']} / {f['Objet']} ({f['Format']})"
            if f["Name"]
            else f"{f['Objet']} ({f['Format']})"
        )
        src.uses(dst, label, f["Protocol"])

    # Views
    vset = {v.strip().lower() for v in views_spec.split(',') if v.strip()}
    if "system" in vset:
        ws.SystemLandscapeView("SystemLandscape", "All systems")
    if "container" in vset:
        for sys_elem in systems_by_id.values():
            if sys_elem.elements:
                ws.ContainerView(sys_elem, f"{sys_elem.name}_Container", f"Containers for {sys_elem.name}")

    # Element styles (et pas de styles relationnels spécifiques)
    ws.Styles(
        {"tag": "ApplicationSystem", "shape": "RoundedBox", "background": "#1168bd", "color": "#ffffff"},
        {"tag": "ApplicationContainer", "shape": "Box", "background": "#438dd5", "color": "#ffffff"},
    )
    return ws


# ------------------------------------------------ main

def main():
    args = parse_args()
    logging.basicConfig(level=args.log_level)

    apps, flows = load_excel(args.file)
    validate(apps, flows)

    ws = build_workspace(apps, flows, args.views)

    args.output.mkdir(parents=True, exist_ok=True)
    out = args.output / "workspace.dsl"
    out.write_text(ws.dump(), encoding="utf-8")
    print("DSL saved →", out)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)
