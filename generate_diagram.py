
#!/usr/bin/env python3
"""Generate Structurizr diagram-as-code from Excel inventory.

Usage:
    python generate_diagram.py flows_applications.xlsx --views system,container --output diagrams
"""

import argparse
import logging
import os
from pathlib import Path
import sys
import pandas as pd

from structurizr.model import Workspace
from structurizr.view import AutoLayout

REQUIRED_FLOW_COLUMNS = {
    "ID", "Name", "Outbound", "Inbound", "Objet", "Protocol", "Format", "Status"
}
REQUIRED_APP_COLUMNS = {
    "ID", "Name", "Application", "Component", "ParentAppID"
}

# --------------- CLI ---------------

def parse_args():
    parser = argparse.ArgumentParser(description="Build Structurizr workspace from Excel.")
    parser.add_argument("file", type=Path, help="flows_applications.xlsx")
    parser.add_argument("--views", default="system,container",
                        help="Comma separated list: system,container")
    parser.add_argument("--filter-protocol", default="", help="Comma separated protocols to keep")
    parser.add_argument("--filter-frequency", default="", help="Comma separated frequencies to keep")
    parser.add_argument("--hide-tags", default="", help="Comma separated relation Status tags to hide")
    parser.add_argument("--output", default="build", type=Path, help="Output directory")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()

# --------------- Data ---------------

def load_data(xlsx_path: Path):
    flows_df = pd.read_excel(xlsx_path, sheet_name="Flows").fillna("")
    apps_df = pd.read_excel(xlsx_path, sheet_name="Applications").fillna("")
    return apps_df, flows_df

def validate_data(apps_df: pd.DataFrame, flows_df: pd.DataFrame):
    missing_flow = REQUIRED_FLOW_COLUMNS - set(flows_df.columns)
    missing_app = REQUIRED_APP_COLUMNS - set(apps_df.columns)
    if missing_flow:
        raise ValueError(f"Missing columns in Flows: {', '.join(missing_flow)}")
    if missing_app:
        raise ValueError(f"Missing columns in Applications: {', '.join(missing_app)}")

    id_set = set(apps_df["ID"])
    name_set = set(apps_df["Name"])

    invalid_parents = apps_df[(apps_df["Component"] == "#") & (~apps_df["ParentAppID"].isin(id_set))]
    if not invalid_parents.empty:
        raise ValueError("ParentAppID invalid in rows: " + ", ".join(map(str, invalid_parents.index.tolist())))

    for col in ("Outbound", "Inbound"):
        invalid = flows_df[~flows_df[col].isin(name_set)]
        if not invalid.empty:
            raise ValueError(f"{col} contains unknown names in rows: " + ", ".join(map(str, invalid.index.tolist())))

    for col in ("Protocol", "Objet", "Format"):
        empty = flows_df[flows_df[col] == ""]
        if not empty.empty:
            raise ValueError(f"{col} empty in rows: " + ", ".join(map(str, empty.index.tolist())))

# --------------- Model ---------------

def build_model(apps_df: pd.DataFrame, flows_df: pd.DataFrame):
    from structurizr.model import Workspace
    workspace = Workspace(name="Applications & Flows", description="Generated from Excel")
    model = workspace.get_model()
    element_by_name = {}

    # Add software systems
    for _, row in apps_df[apps_df["Application"] == "#"].iterrows():
        ss = model.add_software_system(row["Name"], row.get("Description", ""))
        ss.add_tags("ApplicationSystem")
        element_by_name[row["Name"]] = ss

    # Add containers
    apps_dict = apps_df.set_index("ID").to_dict("index")
    for _, row in apps_df[apps_df["Component"] == "#"].iterrows():
        parent_row = apps_dict.get(row["ParentAppID"])
        if not parent_row:
            continue
        parent_sys = element_by_name[parent_row["Name"]]
        c = parent_sys.add_container(row["Name"], row.get("Description", ""), "")
        c.add_tags("ApplicationContainer")
        element_by_name[row["Name"]] = c

    # Add relationships
    for _, row in flows_df.iterrows():
        src = element_by_name[row["Outbound"]]
        dst = element_by_name[row["Inbound"]]
        rel = src.uses(dst, description=row["Objet"], technology=row["Protocol"])
        rel.properties["dataFormat"] = row["Format"]
        if row["Status"]:
            rel.add_tags(row["Status"])
        if row["Frequency"]:
            rel.properties["Frequency"] = row["Frequency"]
    return workspace

# --------------- Views ---------------

def filter_relationships(workspace: Workspace, proto_filter, freq_filter, hide_tags):
    model = workspace.get_model()
    for rel in list(model.get_relationships()):
        if proto_filter and rel.technology.lower() not in proto_filter:
            model.remove_relationship(rel)
            continue
        if freq_filter and rel.properties.get("Frequency", "").lower() not in freq_filter:
            model.remove_relationship(rel)
            continue
        if hide_tags and (set(rel.tags) & hide_tags):
            model.remove_relationship(rel)
            continue

def create_views(workspace: Workspace, views_sel):
    from structurizr.view import AutoLayout, SystemContextView, ContainerView
    views = workspace.get_views()
    styles = views.get_configuration().get_styles()
    styles.add_element_style(tag="ApplicationSystem").shape("RoundedBox")
    styles.add_element_style(tag="ApplicationContainer").shape("Box")
    styles.add_relationship_style(tag="Add").color("#28a745")
    styles.add_relationship_style(tag="Change").color("#ff8c00")
    styles.add_relationship_style(tag="Keep").color("#6c757d")

    if "system" in views_sel:
        scv = views.create_system_context_view(workspace.get_model(), "SystemContext",
                                               "All application systems")
        scv.add_all_software_systems()
        scv.add_all_relationships()
        AutoLayout().apply(scv)
    if "container" in views_sel:
        for ss in workspace.get_model().get_software_systems():
            if not ss.get_containers():
                continue
            cv = views.create_container_view(ss, f"{ss.name}_containers", f"Containers for {ss.name}")
            cv.add(ss)
            cv.add_all_containers()
            cv.add_nearest_neighbours(ss)
            AutoLayout().apply(cv)

# --------------- Export ---------------

def export_workspace(workspace: Workspace, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    workspace.to.dsl(out_dir / "workspace.dsl")
    workspace.to_json_json(out_dir / "workspace.json")

    key = os.getenv("STRUCTURIZR_API_KEY")
    secret = os.getenv("STRUCTURIZR_API_SECRET")
    ws_id = os.getenv("STRUCTURIZR_WORKSPACE_ID")
    if key and secret and ws_id:
        from structurizr.api import StructurizrClient
        client = StructurizrClient(api_key=key, api_secret=secret, workspace_id=int(ws_id))
        client.put_workspace(workspace)
        print(f"Pushed to Structurizr Cloud (workspace ID {ws_id}).")
    else:
        print(f"Workspace saved in {out_dir}. Open with Structurizr-Lite or push manually.")

# --------------- main ---------------

def main():
    args = parse_args()
    logging.basicConfig(level=args.log_level)
    apps_df, flows_df = load_data(args.file)
    validate_data(apps_df, flows_df)
    workspace = build_model(apps_df, flows_df)

    proto_filter = set(p.strip().lower() for p in args.filter_protocol.split(",") if p.strip())
    freq_filter = set(f.strip().lower() for f in args.filter_frequency.split(",") if f.strip())
    hide_tags = set(t.strip() for t in args.hide_tags.split(",") if t.strip())

    filter_relationships(workspace, proto_filter, freq_filter, hide_tags)

    views_sel = set(v.strip().lower() for v in args.views.split(",") if v.strip())
    create_views(workspace, views_sel)

    export_workspace(workspace, args.output)

    m = workspace.get_model()
    print(f"Done! Systems: {len(m.get_software_systems())} | Containers: {len(m.get_containers())} | Relationships: {len(m.get_relationships())}")

if __name__ == "__main__":
    main()
