"""
Create / update DB tables via Alembic migrations.

Run:
  uv run --directory backend python scripts/db/upgrade_schema.py

Optional:
  uv run --directory backend python scripts/db/upgrade_schema.py --revision head

Requirements:
- `DATABASE_URL` must be set (backend/.env or environment variable).
  See `backend/.env.example`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
if str(_BACKEND_ROOT) not in sys.path:
    # Ensure `import app...` works for Alembic env.py.
    sys.path.insert(0, str(_BACKEND_ROOT))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Alembic migrations to create/update DB tables.",
    )
    parser.add_argument(
        "--revision",
        default="head",
        help="Alembic revision to upgrade to (default: head).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)

    alembic_ini = _BACKEND_ROOT / "alembic.ini"
    alembic_dir = _BACKEND_ROOT / "alembic"

    if not alembic_ini.is_file():
        raise FileNotFoundError(f"Missing {alembic_ini}")
    if not alembic_dir.is_dir():
        raise FileNotFoundError(f"Missing {alembic_dir}")

    config = Config(str(alembic_ini))
    # Be explicit in case the script is run from a different working directory.
    config.set_main_option("script_location", str(alembic_dir))

    command.upgrade(config, args.revision)


if __name__ == "__main__":
    main()

