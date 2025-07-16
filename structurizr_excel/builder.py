"""
builder.py – construit le Workspace Structurizr DSL :
Organisation ▸ Application (Group) ▸ Container.
Une CustomView par BusinessProcess regroupe les conteneurs par application.
"""

import re
import argparse, logging, sys
from typing import Dict, Set
from types import SimpleNamespace
from pystructurizr.dsl import Workspace, View, Dumper, Container, Group  # type: ignore
from .styles import STYLES

BASE_SYS_NAME = "Process Views"
# ---------- utilitaires --------------------------------------------
def split_multi(txt) -> Set[str]:
    if not isinstance(txt, str) or not txt.strip():
        return set()
    return {t for t in re.split(r"[;,\s]+", txt.lower()) if t}

def camel(txt: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[^0-9a-zA-Z]", txt) if w)

# ---------- patches dump -------------------------------------------
def _view_dump(self: View, dumper: Dumper):  # type: ignore
    elem_part = self.element.instname if self.element else ""
    key_part  = f" {self.name}" if self.name else ""
    dumper.add(f"{self.viewkind.value} {elem_part}{key_part} {{")
    dumper.indent()
    if self.description:
        dumper.add(f'description "{self.description}"')
    # Écrit chaque include explicitement
    for inc in dict.fromkeys(self.includes):
        dumper.add(f'include {inc.instname}')
    dumper.add('autoLayout lr')
    dumper.outdent()
    dumper.add('}')
View.dump = _view_dump  # type: ignore

_original_container_dump = Container.dump  # type: ignore

def _container_dump(self: Container, dumper: Dumper):  # type: ignore
    parent = getattr(self, "_parent", None)
    if isinstance(parent, Group):
        # Required syntax: <alias> = element <alias> "Name" "Desc" { tags ... }
        dumper.add(f'{self.instname} = container {self.instname} "{self.name}" "{self.description}" {{')
        dumper.indent()
        if self.tags:
            dumper.add(f'tags "{", ".join(self.tags)}"')
        dumper.outdent()
        dumper.add('}')
    else:
        _original_container_dump(self, dumper)

Container.dump = _container_dump  # type: ignore  # type: ignore  # type: ignore  # type: ignore


# ---------- ajoute CustomView --------------------------------------
_custom_kind = SimpleNamespace(value="custom")
def _custom_view(self, key, desc):
    v = View(_custom_kind, None, key, desc)
    self.views.append(v)
    return v
setattr(Workspace, "CustomView", _custom_view)

# ---------- build_workspace ----------------------------------------
def build_workspace(apps, flows, procs) -> Workspace:
    ws = Workspace()
    model = ws.Model(name="model")                           # ≤— évite 'str' object bug
    elem_by_id: Dict[str, any] = {}
    groups_by_id: Dict[str, any] = {}
    container_parent: Dict[any, any] = {}

    base_sys = model.SoftwareSystem(BASE_SYS_NAME)
            # Organisations as SoftwareSystems, Applications as Groups
    org_systems: Dict[str, any] = {}
    for _, row in apps[apps["Application"] == "#"].iterrows():
        org_name = row.get("Organisation", "Unknown") or "Unknown"
        sys = org_systems.get(org_name)
        if not sys:
            sys = model.SoftwareSystem(org_name)
            org_systems[org_name] = sys
        app_grp = sys.Group(row["Name"])
        app_grp.tags.extend(["ApplicationGroup", f"status:{row['Status'] or 'keep'}"])
        elem_by_id[row["ID"]] = app_grp
        groups_by_id[row["ID"]] = app_grp

    # Containers
    for _, row in apps[apps["Component"] == "#"].iterrows():
        parent = groups_by_id.get(row["ParentAppID"])
        if not parent:
            logging.warning("Skip container %s: parent %s missing", row["ID"], row["ParentAppID"])
            continue
        cont = parent.Container(row["Name"], row.get("Description", ""), technology="")
        cont._parent = parent  # Mark parent grouprow["Name"], row.get("Description", ""), technology="")
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

        # ContainerView per BusinessProcess (based on base_sys)
    for _, bp in procs.iterrows():
        pid = bp["ID"].strip()
        if not pid:
            continue
        pname = bp["Name"].strip() or pid
        tag   = f"proc:{pid.lower()}"
        view  = ws.ContainerView(base_sys, f"Proc{camel(pname)}", f"{pname} (process view)")

        # Inclure uniquement les conteneurs et leurs groupes portant le tag
        for grp in groups_by_id.values():
            for c in grp.elements:
                logging.debug(f"{tag}")
                logging.debug(f"proc:{c.tags}")
                if tag in c.tags:
                    view.include(c)

    ws.Styles(*STYLES)
    return ws
