"""Split legacy yahoo_calendar_event into per-kind tables

If the DB still has ``yahoo_calendar_event`` (from an older 808088886e2b revision that created
one polymorphic table), copy rows into ``yahoo_calendar_*`` and drop the old table.

If the four per-kind tables already exist and the legacy table is gone, this migration is a no-op.

Revision ID: c4f2b1a8d3e0
Revises: 808088886e2b
Create Date: 2026-03-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision: str = "c4f2b1a8d3e0"
down_revision: Union[str, Sequence[str], None] = "808088886e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND_TABLES: tuple[tuple[str, str], ...] = (
    ("earnings", "yahoo_calendar_earnings"),
    ("economic_events", "yahoo_calendar_economic_events"),
    ("splits", "yahoo_calendar_splits"),
    ("ipo", "yahoo_calendar_ipo"),
)


def _calendar_columns():
    return [
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("limit_applied", sa.Integer(), nullable=True),
        sa.Column("offset_applied", sa.Integer(), nullable=True),
        sa.Column("fetch_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("row_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    ]


def _create_calendar_table(name: str) -> None:
    op.create_table(name, *_calendar_columns())
    op.create_index(f"ix_{name}_window_start", name, ["window_start"])
    op.create_index(f"ix_{name}_window_end", name, ["window_end"])
    op.create_index(f"ix_{name}_fetched_at", name, ["fetched_at"])
    op.create_index(f"ix_{name}_window", name, ["window_start", "window_end"])


def _drop_calendar_table(name: str) -> None:
    op.drop_index(f"ix_{name}_window", table_name=name)
    op.drop_index(f"ix_{name}_fetched_at", table_name=name)
    op.drop_index(f"ix_{name}_window_end", table_name=name)
    op.drop_index(f"ix_{name}_window_start", table_name=name)
    op.drop_table(name)


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    tables = set(insp.get_table_names(schema="public"))

    new_names = [t for _, t in _KIND_TABLES]
    for n in new_names:
        if n not in tables:
            _create_calendar_table(n)
            tables.add(n)

    if "yahoo_calendar_event" not in tables:
        return

    for cal_type, dest in _KIND_TABLES:
        conn.execute(
            text(
                f"""
                INSERT INTO {dest} (
                    window_start, window_end, limit_applied, offset_applied,
                    fetch_params, row_data, fetched_at
                )
                SELECT
                    window_start, window_end, limit_applied, offset_applied,
                    fetch_params, row_data, fetched_at
                FROM yahoo_calendar_event
                WHERE calendar_type = :cal_type
                """
            ),
            {"cal_type": cal_type},
        )

    op.drop_table("yahoo_calendar_event")


def downgrade() -> None:
    op.create_table(
        "yahoo_calendar_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("calendar_type", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("limit_applied", sa.Integer(), nullable=True),
        sa.Column("offset_applied", sa.Integer(), nullable=True),
        sa.Column("fetch_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("row_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "calendar_type IN ('earnings', 'economic_events', 'splits', 'ipo')",
            name="ck_yahoo_calendar_event_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_yahoo_calendar_event_calendar_type",
        "yahoo_calendar_event",
        ["calendar_type"],
    )
    op.create_index(
        "ix_yahoo_calendar_event_window_start",
        "yahoo_calendar_event",
        ["window_start"],
    )
    op.create_index(
        "ix_yahoo_calendar_event_window_end",
        "yahoo_calendar_event",
        ["window_end"],
    )
    op.create_index(
        "ix_yahoo_calendar_event_fetched_at",
        "yahoo_calendar_event",
        ["fetched_at"],
    )
    op.create_index(
        "ix_yahoo_calendar_event_type_window",
        "yahoo_calendar_event",
        ["calendar_type", "window_start", "window_end"],
    )

    conn = op.get_bind()
    for cal_type, src in _KIND_TABLES:
        conn.execute(
            text(
                f"""
                INSERT INTO yahoo_calendar_event (
                    calendar_type,
                    window_start, window_end, limit_applied, offset_applied,
                    fetch_params, row_data, fetched_at
                )
                SELECT
                    :cal_type,
                    window_start, window_end, limit_applied, offset_applied,
                    fetch_params, row_data, fetched_at
                FROM {src}
                """
            ),
            {"cal_type": cal_type},
        )

    for _, t in _KIND_TABLES:
        _drop_calendar_table(t)
