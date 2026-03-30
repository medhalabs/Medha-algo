#!/usr/bin/env python3
"""Entry point for subprocess upsert (see ``MEDHA_UPSERT_SUBPROCESS`` in the DAG)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: run_dhan_yahoo_upsert.py <config.json>", file=sys.stderr)
        raise SystemExit(2)
    cfg_path = Path(sys.argv[1])
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    airflow_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(airflow_root / "dags"))
    from lib.dhan_yahoo_upsert_worker import run_upsert_from_cfg

    run_upsert_from_cfg(cfg)


if __name__ == "__main__":
    main()
