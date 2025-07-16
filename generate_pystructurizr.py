#!/usr/bin/env python3
"""Generate Structurizr DSL via custom DSL — IDs in Flows, names in diagram  **v8**.

### Changements majeurs v8
1. **Vues par processus = 1 ContainerView par système concerné**
   - Pour chaque processus `P` et chaque *SoftwareSystem* `S` ayant au moins un conteneur tagué `proc:P`, on crée la vue :
     ```
     container proc_<P>_<S> "Business process — <P name> / <S>"
     ```
   - Elle inclut `S` et uniquement ses conteneurs portant le tag `proc:P` ; les autres sont exclus.
   - Ainsi, les conteneurs apparaissent bien (contrairement à SystemLandscapeView, limité aux systèmes).
2. **Propagation automatique** du tag `proc:*` du conteneur vers son système parent (afin que le système figure aussi dans la vue).
3. **Suppression** de l’ancienne boucle _SystemLandscapeView proc_* (désormais inutile).
4. **Logs DEBUG** indiquant les vues créées et les éléments inclus/exclus.

---
Usage :
```bash
python generate_pystructurizr_id_v8.py flows_applications.xlsx \
       --output build --log-level DEBUG
```
"""

import argparse
import logging
import sys
import re
from pathlib import Path
from typing import Tuple, Set, Dict

import pandas as pd
from pystructurizr.dsl import View, Dumper, Workspace  # type: ignore

# -------------------------------------------------------------------
# Monkey-patch View.dump to embed the *key* (self.name) after element
# -------------------------------------------------------------------

def _patched_view_dump(self: View, dumper: Dumper) -> None:  # noqa: D401
    elem_part = self.element.instname if self.element else ""
    key_part = f" {self.name}" if self.name else ""
    dumper.add(f"{self.viewkind.value} {elem_part}{key_part} {{")
    dumper.indent()
    if self.description:
        dumper.add(f'description "{self.description}"')
    dumper.add('include *')
    for include in self.includes:
        dumper.add(f'include {include.instname}')
    for exclude in self.excludes:
        dumper.add(f'exclude {exclude.instname}')
    dumper.add('autoLayout')
    dumper.outdent()
    dumper.add('}')

View.dump = _patched_view_dump  # type: ignore

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------



REQUIRED_APP = {
    "ID", "Name", "Application", "Component", "ParentAppID", "Status"
}
REQUIRED_FLOW = {
    "ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Tags", "BusinessProcess"
}

# ------------------------------------------------ CLI

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Structurizr workspace from Excel (IDs mode)")
    p.add_argument("file", type=Path, help="flows_applications.xlsx")
    p.add_argument("--output", type=Path, default=Path("build"), help="Output directory")
    p.add_argument("--views", default="system,container", help="Standard views to generate (comma‑sep)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()

# ------------------------------------------------ Excel loading

def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")
    apps = pd.read_excel(path, sheet_name="Applications", **kw)
    flows = pd.read_excel(path, sheet_name="Flows", **kw)
    try:
        processes = pd.read_excel(path, sheet_name="BusinessProcesses", **kw)
    except ValueError:
        processes = pd.DataFrame(columns=["ID", "Name"])

    for col in ("ID", "ParentAppID"):
        apps[col] = apps[col].str.strip()
    for col in ("Outbound", "Inbound", "Tags", "BusinessProcess"):
        flows[col] = flows[col].str.strip()

    apps["Status"] = apps["Status"].str.strip().str.lower()
    return apps, flows, processes

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

# ------------------------------------------------ Helpers

def split_multi(text: str) -> Set[str]:
    return {t for t in re.split(r"[;,\s]+", (text or "").lower()) if t}

# ------------------------------------------------ Workspace builder

def build_workspace(apps: pd.DataFrame, flows: pd.DataFrame, processes: pd.DataFrame, views_spec: str) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")
   
    elem_by_id: Dict[str, any] = {}
    systems_by_id: Dict[str, any] = {}
    container_parent: Dict[any, any] = {}

    # --- Elements : SoftwareSystems
    for _, row in apps[apps["Application"] == "#"].iterrows():
        sys_el = model.SoftwareSystem(row["Name"], row.get("Description", ""))
        sys_el.tags.extend(["ApplicationSystem", f"status:{row['Status'] or 'keep'}"])
        elem_by_id[row["ID"]] = sys_el
        systems_by_id[row["ID"]] = sys_el

    # --- Elements : Containers
    for _, row in apps[apps["Component"] == "#"].iterrows():
        parent = systems_by_id.get(row["ParentAppID"])
        if not parent:
            logging.warning("Skip container %s: parent %s missing", row["ID"], row["ParentAppID"])
            continue
        cont = parent.Container(row["Name"], row.get("Description", ""), technology="")
        cont.tags.extend(["ApplicationContainer", f"status:{row['Status'] or 'keep'}"])
        elem_by_id[row["ID"]] = cont
        container_parent[cont] = parent

    # --- Relationships & tagging proc:*
    seen = set()
    for _, f in flows.iterrows():
        src, dst = elem_by_id.get(f["Outbound"]), elem_by_id.get(f["Inbound"])
        if not src or not dst:
            continue
        key = (f["Outbound"], f["Inbound"], f["Objet"], f["Protocol"], f["Format"])
        if key in seen:
            continue
        seen.add(key)

        label = f"{f['Name']} / {f['Objet']} ({f['Format']})" if f["Name"] else f"{f['Objet']} ({f['Format']})"
        src.uses(dst, label, f["Protocol"])

        for proc in split_multi(f["BusinessProcess"]):
            tag = f"proc:{proc}"
            for el in (src, dst):
                if tag not in el.tags:
                    el.tags.append(tag)

    # --- Propagate proc:* tags from containers to their parent systems
    for cont, parent in container_parent.items():
        for tag in cont.tags:
            if tag.startswith("proc:") and tag not in parent.tags:
                parent.tags.append(tag)

    # --- Standard views (system/container global)
    vset = {v.strip().lower() for v in views_spec.split(',') if v.strip()}
    if "system" in vset:
        ws.SystemLandscapeView("SystemLandscape", "All systems")
    if "container" in vset:
        for sys_el in systems_by_id.values():
            if sys_el.elements:
                ws.ContainerView(sys_el, f"{sys_el.name}_Container", f"Containers for {sys_el.name}")

    # --- Business‑process ContainerViews (par système)
    for _, prow in processes.iterrows():
        pid = prow["ID"].strip()
        if not pid:
            continue
        pname = prow["Name"].strip() or pid
        tag = f"proc:{pid.lower()}"

        for sys_id, sys_el in systems_by_id.items():
            # Conteneurs concernés dans ce système
            conts = [c for c in sys_el.elements if tag in c.tags]
            if not conts:
                continue  # Ce système n'est pas concerné par ce processus

         
            def camel(s: str) -> str:
                return ''.join(word.capitalize() for word in re.split(r"[^0-9a-zA-Z]", s) if word)

            safe_pname = camel(pname)
            safe_sysname = camel(sys_el.name)
            view_key = f"Proc{safe_pname}{safe_sysname}"
            view_title = f"{pname} – {sys_el.name} (process view)"
            view = ws.ContainerView(sys_el, view_key, view_title)

            # Inclure uniquement ce qu'il faut
            view.include(sys_el)
            for c in conts:
                view.include(c)

            # Exclure les autres conteneurs du système
            for c in sys_el.elements:
                if c not in conts:
                    view.exclude(c)

            logging.debug("[view %s] system=%s containers=%s", view_key, sys_el.name, [c.name for c in conts])

    # --- Styles
    ws.Styles(
        {"tag": "ApplicationSystem", "shape": "RoundedBox", "background": "#1168bd", "color": "#ffffff"},
        {"tag": "ApplicationContainer", "shape": "Box", "background": "#438dd5", "color": "#ffffff"},
        {"tag": "status:add", "shape": "Box", "background": "#28a745", "color": "#ffffff"},
        {"tag": "status:change", "shape": "Box", "background": "#6f42c1", "color": "#ffffff"},
        {"tag": "status:remove", "shape": "Box", "background": "#d9534f", "color": "#ffffff"},
    )

    return ws

# ------------------------------------------------ main

def main():
    args = parse_args()
    logging.basicConfig(level=args.log_level)
    apps, flows, processes = load_excel(args.file)
    validate(apps, flows)

    ws = build_workspace(apps, flows, processes, args.views)

    args.output.mkdir(parents=True, exist_ok=True)

        # Ensure output dir
    args.output.mkdir(parents=True, exist_ok=True)
    dsl_path = args.output / "workspace.dsl"
    dsl_path.write_text(ws.dump(), encoding="utf-8")
    logging.info("DSL saved → %s", dsl_path)

    if args.log_level == "DEBUG":
        print("==== DSL content ====")
        print(ws.dump())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)