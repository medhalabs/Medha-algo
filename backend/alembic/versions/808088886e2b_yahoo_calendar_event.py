"""yahoo calendar tables (one per kind)

Revision ID: 808088886e2b
Revises: 5bb323ab0fd5
Create Date: 2026-03-30 22:41:22.212061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "808088886e2b"
down_revision: Union[str, Sequence[str], None] = "5bb323ab0fd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    for t in (
        "yahoo_calendar_earnings",
        "yahoo_calendar_economic_events",
        "yahoo_calendar_splits",
        "yahoo_calendar_ipo",
    ):
        _create_calendar_table(t)


def downgrade() -> None:
    for t in (
        "yahoo_calendar_ipo",
        "yahoo_calendar_splits",
        "yahoo_calendar_economic_events",
        "yahoo_calendar_earnings",
    ):
        _drop_calendar_table(t)
