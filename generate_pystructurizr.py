#!/usr/bin/env python3
"""Generate Structurizr DSL via pystructurizr — IDs in Flows, names in diagram  **v5**.

### Nouveautés v5
1. **Couleurs élémentaires pilotées par `Applications.Status`**  
   | Status   | Couleur | Code |
   |----------|---------|------|
   | Keep/—   | palette par défaut Structurizr |
   | Change   | violet `#6f42c1` |
   | Add      | vert `#28a745` |
   | Remove   | rouge `#d9534f` |

2. **Filtrage par tag des flux**  
   *Paramètre CLI :* `--filter-tag beta,critical`  
   Seuls les flux dont la colonne **Tags** contient l’un des tags spécifiés (séparateur virgule ou espace) sont conservés ; les autres relations ne sont pas générées.

3. Colonnes obligatoires :  
   *Applications* : ajoute `Status`  
   *Flows* : ajoute `Tags` (multivalué).

---
Usage :
```bash
python generate_pystructurizr_id_v5.py flows_applications.xlsx \
       --filter-tag beta,critical \
       --output diagrams
```

Dépendances : `pip install git+https://github.com/nielsvanspauwen/pystructurizr.git pandas openpyxl`
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Tuple, Set

import pandas as pd
from pystructurizr.dsl import Workspace

REQUIRED_APP = {
    "ID", "Name", "Application", "Component", "ParentAppID", "Status"
}
REQUIRED_FLOW = {
    "ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Tags"
}

# ------------------------------------------------ CLI

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Structurizr workspace from Excel (IDs mode)")
    p.add_argument("file", type=Path, help="flows_applications.xlsx")
    p.add_argument("--output", type=Path, default=Path("build"), help="Output directory")
    p.add_argument("--views", default="system,container", help="Views to generate (comma‑sep)")
    p.add_argument("--filter-tag", default="", help="Filter flows by tag list (comma‑sep)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()

# ------------------------------------------------ Excel loading

def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")
    apps = pd.read_excel(path, sheet_name="Applications", **kw)
    flows = pd.read_excel(path, sheet_name="Flows", **kw)

    # Trim
    for col in ("ID", "ParentAppID"):
        apps[col] = apps[col].str.strip()
    for col in ("Outbound", "Inbound", "Tags"):
        flows[col] = flows[col].str.strip()

    apps["Status"] = apps["Status"].str.strip().str.lower()
    return apps, flows

# ------------------------------------------------ Validation

def validate(apps: pd.DataFrame, flows: pd.DataFrame):
    if m := REQUIRED_APP - set(apps.columns):
        raise ValueError(f"Applications missing: {', '.join(m)}")
    if m := REQUIRED_FLOW - set(flows.columns):
        raise ValueError(f"Flows missing: {', '.join(m)}")

    idset = set(apps["ID"])
    bad_parent = apps[(apps["Component"] == "#") & (~apps["ParentAppID"].isin(idset))]
    if not bad_parent.empty:
        raise ValueError("Invalid ParentAppID rows: " + ", ".join(map(str, bad_parent.index)))

    for col in ("Outbound", "Inbound"):
        miss = flows[~flows[col].isin(idset)]
        if not miss.empty:
            raise ValueError(f"{col} unknown IDs rows: {', '.join(map(str, miss.index))}")

    for col in ("Protocol", "Objet", "Format"):
        empty = flows[flows[col] == ""]
        if not empty.empty:
            raise ValueError(f"Column {col} empty rows: {', '.join(map(str, empty.index))}")

# ------------------------------------------------ Helper

def parse_tag_cell(cell: str) -> Set[str]:
    # Split by comma / semicolon / space & lowercase
    return {t.strip().lower() for t in re.split(r"[;,\s]+", cell) if t.strip()}

import re

# ------------------------------------------------ Workspace builder

def build_workspace(apps: pd.DataFrame, flows: pd.DataFrame, views_spec: str, tag_filter: Set[str]) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")

    elem_by_id, systems_by_id = {}, {}

    colour_map = {
        "add": "#28a745",
        "change": "#6f42c1",  # violet
        "remove": "#d9534f",
        "keep": None,
    }

    # Systems & Containers -------------------------------------------------
    for _, row in apps[apps["Application"] == "#"].iterrows():
        sys_el = model.SoftwareSystem(row["Name"], row.get("Description", ""))
        sys_el.tags.append("ApplicationSystem")
        col = colour_map.get(row["Status"] or "keep")
        if col:
            sys_el.color = col
        elem_by_id[row["ID"]] = sys_el
        systems_by_id[row["ID"]] = sys_el

    for _, row in apps[apps["Component"] == "#"].iterrows():
        parent = systems_by_id.get(row["ParentAppID"])
        if not parent:
            logging.warning("Skip container %s: parent %s missing", row["ID"], row["ParentAppID"])
            continue
        cont = parent.Container(row["Name"], row.get("Description", ""), technology="")
        cont.tags.append("ApplicationContainer")
        col = colour_map.get(row["Status"] or "keep")
        if col:
            cont.color = col
        elem_by_id[row["ID"]] = cont

    # Relationships with dedup & tag‑filter --------------------------------
    seen = set()
    for _, f in flows.iterrows():
        # Filter by tag if requested
        if tag_filter:
            flow_tags = parse_tag_cell(f["Tags"])
            if not (flow_tags & tag_filter):
                continue

        src, dst = elem_by_id.get(f["Outbound"]), elem_by_id.get(f["Inbound"])
        if not src or not dst:
            continue
        dedup = (f["Outbound"], f["Inbound"], f["Objet"], f["Protocol"], f["Format"])
        if dedup in seen:
            continue
        seen.add(dedup)

        label = f"{f['Name']} / {f['Objet']} ({f['Format']})" if f["Name"] else f"{f['Objet']} ({f['Format']})"
        src.uses(dst, label, f["Protocol"])

    # Views ---------------------------------------------------------------
    vset = {v.strip().lower() for v in views_spec.split(',') if v.strip()}
    if "system" in vset:
        ws.SystemLandscapeView("SystemLandscape", "All systems (filtered)")
    if "container" in vset:
        for sys_el in systems_by_id.values():
            if sys_el.elements:
                ws.ContainerView(sys_el, f"{sys_el.name}_Container", f"Containers for {sys_el.name}")

    # Styles (elements seulement)
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

    tag_filter = {t.strip().lower() for t in args.filter_tag.split(',') if t.strip()}

    ws = build_workspace(apps, flows, args.views, tag_filter)

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
