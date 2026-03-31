DB schema scripts

This folder contains scripts related to database schema creation/updates.

Main entrypoint:

- `upgrade_schema.py` runs Alembic migrations (`alembic upgrade head`) so tables are created/updated automatically on any machine.

