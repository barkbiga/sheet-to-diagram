#!/usr/bin/env python3
"""Generate Structurizr DSL from Excel — **v10 (Group‑centric)**
---------------------------------------------------------------
* Les **SoftwareSystems sont remplacés par des Group** dans le `model`.
* Une **CustomView** par processus affiche les conteneurs regroupés par leur
  groupe (ancien système).
* Pas de vues globales System/Container (plus de système).
* Styles adaptés (tag `ApplicationGroup`).
"""

import argparse
import logging
import sys
import re
from pathlib import Path
from typing import Tuple, Set, Dict

import pandas as pd
from pystructurizr.dsl import View, Dumper, Workspace  # type: ignore
from types import SimpleNamespace

# -------------------------------------------------------------------
# Patch View.dump – gère group_map lorsqu’elle est fournie
# -------------------------------------------------------------------

def _patched_view_dump(self: View, dumper: Dumper) -> None:  # noqa: D401
    key_part = f" {self.name}" if self.name else ""
    dumper.add(f"{self.viewkind.value}{key_part} {{")
    dumper.indent()
    if self.description:
        dumper.add(f'description "{self.description}"')

    if hasattr(self, "group_map"):
        for grp_name, cont_list in self.group_map.items():
            dumper.add(f'group "{grp_name}" {{')
            dumper.indent()
            for c in cont_list:
                dumper.add(f'include {c.instname}')
            dumper.outdent()
            dumper.add('}')
    else:
        for inc in dict.fromkeys(self.includes):
            dumper.add(f'include {inc.instname}')

    dumper.add('autoLayout lr')
    dumper.outdent()
    dumper.add('}')

View.dump = _patched_view_dump  # type: ignore

# -------------------------------------------------------------------
# Add CustomView capability
# -------------------------------------------------------------------
_custom_kind = SimpleNamespace(value="custom")

def _custom_view(self, key: str, description: str):  # noqa: D401
    v = View(_custom_kind, None, key, description)
    self.views.append(v)
    return v

setattr(Workspace, "CustomView", _custom_view)

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------
REQUIRED_APP = {"ID", "Name", "Application", "Component", "ParentAppID", "Status"}
REQUIRED_FLOW = {
    "ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Tags", "BusinessProcess"
}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def split_multi(text: str) -> Set[str]:
    return {t for t in re.split(r"[;,\s]+", (text or "").lower()) if t}

def camel(s: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[^0-9a-zA-Z]", s) if w)

# -------------------------------------------------------------------
# Load & validate Excel
# -------------------------------------------------------------------

def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kw = dict(dtype=str, keep_default_na=False, engine="openpyxl")
    apps = pd.read_excel(path, sheet_name="Applications", **kw)
    flows = pd.read_excel(path, sheet_name="Flows", **kw)
    try:
        procs = pd.read_excel(path, sheet_name="BusinessProcesses", **kw)
    except ValueError:
        procs = pd.DataFrame(columns=["ID", "Name"])

    # strip
    for col in ("ID", "ParentAppID"):
        apps[col] = apps[col].str.strip()
    for col in ("Outbound", "Inbound", "Tags", "BusinessProcess"):
        flows[col] = flows[col].str.strip()
    apps["Status"] = apps["Status"].str.strip().str.lower()
    return apps, flows, procs


def validate(apps: pd.DataFrame, flows: pd.DataFrame):
    if diff := REQUIRED_APP - set(apps.columns):
        raise ValueError(f"Applications missing columns: {', '.join(diff)}")
    if diff := REQUIRED_FLOW - set(flows.columns):
        raise ValueError(f"Flows missing columns: {', '.join(diff)}")

    ids = set(apps["ID"])
    bad_parent = apps[(apps["Component"] == "#") & (~apps["ParentAppID"].isin(ids))]
    if not bad_parent.empty:
        raise ValueError("Invalid ParentAppID rows: " + ", ".join(map(str, bad_parent.index)))

    for col in ("Outbound", "Inbound"):
        bad = flows[~flows[col].isin(ids)]
        if not bad.empty:
            raise ValueError(f"{col} unknown IDs rows: {', '.join(map(str, bad.index))}")

# -------------------------------------------------------------------
# Workspace builder
# -------------------------------------------------------------------

def build_workspace(apps: pd.DataFrame, flows: pd.DataFrame, procs: pd.DataFrame) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")

    elem_by_id: Dict[str, any] = {}
    groups_by_id: Dict[str, any] = {}
    container_parent: Dict[any, any] = {}

    # Groups
    for _, row in apps[apps["Application"] == "#"].iterrows():
        g = model.Group(row["Name"])
        g.tags.extend(["ApplicationGroup", f"status:{row['Status'] or 'keep'}"])
        elem_by_id[row["ID"]] = g
        groups_by_id[row["ID"]] = g

    # Containers
    for _, row in apps[apps["Component"] == "#"].iterrows():
        parent = groups_by_id.get(row["ParentAppID"])
        if not parent:
            logging.warning("Skip container %s: parent %s missing", row["ID"], row["ParentAppID"])
            continue
        cont = parent.Container(row["Name"], row.get("Description", ""), technology="")
        cont.tags.extend(["ApplicationContainer", f"status:{row['Status'] or 'keep'}"])
        elem_by_id[row["ID"]] = cont
        container_parent[cont] = parent

    # Relationships + tag proc:* on containers/groups
    seen = set()
    for _, f in flows.iterrows():
        src, dst = elem_by_id.get(f["Outbound"]), elem_by_id.get(f["Inbound"])
        if not src or not dst:
            continue
        k = (f["Outbound"], f["Inbound"], f["Objet"], f["Protocol"], f["Format"])
        if k in seen:
            continue
        seen.add(k)
        desc = f["Name"] or f["Objet"]
        src.uses(dst, desc, f["Protocol"])
        for proc in split_multi(f["BusinessProcess"]):
            tag = f"proc:{proc}"
            for el in (src, dst):
                if tag not in el.tags:
                    el.tags.append(tag)

    # Propagate tags to groups
    for cont, grp in container_parent.items():
        for tag in cont.tags:
            if tag.startswith("proc:") and tag not in grp.tags:
                grp.tags.append(tag)

    # CustomView per process
    for _, prow in procs.iterrows():
        pid = prow["ID"].strip()
        if not pid:
            continue
        pname = prow["Name"].strip() or pid
        tag = f"proc:{pid.lower()}"
        view = ws.CustomView(f"Proc{camel(pname)}", f"{pname} (process view)")

        group_map: Dict[str, list] = {}
        for grp in groups_by_id.values():
            conts = [c for c in grp.elements if tag in c.tags]
            if conts:
                group_map[grp.name] = conts
        view.group_map = group_map  # type: ignore
        logging.debug("Process %s → %d groups", pid, len(group_map))

    # Styles
    ws.Styles(
        {"tag": "ApplicationGroup", "background": "#1168bd", "color": "#ffffff", "shape": "RoundedBox"},
        {"tag": "ApplicationContainer", "background": "#438dd5", "color": "#ffffff"},
        {"tag": "status:add", "background": "#28a745", "color": "#ffffff"},
        {"tag": "status:change", "background": "#6f42c1", "color": "#ffffff"},
        {"tag": "status:remove", "background": "#d9534f", "color": "#ffffff"},
    )

    return ws

# -------------------------------------------------------------------
# CLI + main
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("excel")
    parser.add_argument("--output", default="build")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)
    apps, flows, procs = load_excel(Path(args.excel))
    validate(apps, flows)
    ws = build_workspace(apps, flows, procs)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "workspace.dsl").write_text(ws.dump(), encoding="utf-8")
    logging.info("DSL saved → %s", out / "workspace.dsl")

    if args.log_level.upper() == "DEBUG":
        print(ws.dump())

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(e)
        sys.exit(1)
