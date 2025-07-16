"""
loader.py – lecture et validation du fichier Excel.
"""

from pathlib import Path
from typing import Tuple, Set
import pandas as pd

REQUIRED_APP: Set[str] = {
    "ID", "Name", "Application", "Component", "ParentAppID", "Status", "Organisation"
}
REQUIRED_FLOW: Set[str] = {
    "ID", "Name", "Outbound", "Inbound", "Objet",
    "Protocol", "Format", "Tags", "BusinessProcess"
}

def _read(sheet: str, path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, dtype=str, engine="openpyxl").fillna("")
    # Nettoie uniquement les colonnes de type objet (str)
    for col in df.select_dtypes(include="object"):
        df[col] = df[col].str.strip()
    return df


def load_excel(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    apps  = _read("Applications", path)
    flows = _read("Flows",        path)
    try:
        procs = _read("BusinessProcesses", path)
    except ValueError:
        procs = pd.DataFrame(columns=["ID", "Name"])
    
    apps["Status"] = apps["Status"].str.lower()
    
    return apps, flows, procs

def validate(apps: pd.DataFrame, flows: pd.DataFrame) -> None:
    if m := REQUIRED_APP - set(apps.columns):
        raise ValueError(f"Applications missing columns: {', '.join(m)}")
    if m := REQUIRED_FLOW - set(flows.columns):
        raise ValueError(f"Flows missing columns: {', '.join(m)}")

    ids = set(apps["ID"])
    bad_parent = apps[(apps["Component"] == "#") & (~apps["ParentAppID"].isin(ids))]
    if not bad_parent.empty:
        raise ValueError("Invalid ParentAppID rows: " + ", ".join(map(str, bad_parent.index)))

    for col in ("Outbound", "Inbound"):
        bad = flows[~flows[col].isin(ids)]
        if not bad.empty:
            raise ValueError(f"{col} unknown IDs rows: {', '.join(map(str, bad.index))}")
