#!/usr/bin/env python3
"""
cli.py – point d’entrée exécutable
"""
import argparse, logging, sys
from pathlib import Path


from structurizr_excel.loader  import load_excel, validate
from structurizr_excel.builder import build_workspace

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("excel", help="flows_applications.xlsx")
    p.add_argument("--output", default="build", help="Output folder")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    args = p.parse_args()

    logging.basicConfig(level=args.log_level)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    apps, flows, procs = load_excel(Path(args.excel))
    logging.debug("File loaded")
    validate(apps, flows)
    logging.debug("File validated")
    ws = build_workspace(apps, flows, procs)

    dsl_path = output / "workspace.dsl"
    dsl_path.write_text(ws.dump(), encoding="utf-8")
    logging.info("DSL saved → %s", dsl_path)



if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error(exc)
        sys.exit(1)
