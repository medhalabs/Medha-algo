#!/usr/bin/env python3
"""Subprocess entry for Yahoo calendar DB sync (fork-safe; see ``medha_yahoo_calendar_sync`` DAG)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend = repo_root / "backend"
    script = backend / "scripts" / "sync_yahoo_calendar_to_db.py"
    if not script.is_file():
        print(f"Missing {script}", file=sys.stderr)
        raise SystemExit(2)
    extra = sys.argv[1:]
    r = subprocess.run(
        ["uv", "run", "--directory", str(backend), "python", str(script), *extra],
        cwd=str(repo_root),
    )
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
