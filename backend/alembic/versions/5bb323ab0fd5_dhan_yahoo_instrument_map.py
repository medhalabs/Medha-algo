"""dhan_yahoo_instrument_map

Revision ID: 5bb323ab0fd5
Revises: 3abba15c21f7
Create Date: 2026-03-29 21:17:25.494001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5bb323ab0fd5'
down_revision: Union[str, Sequence[str], None] = '3abba15c21f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dhan_yahoo_instrument_map",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dhan_security_id", sa.BigInteger(), nullable=True),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("dhan_exch_id", sa.String(length=8), nullable=False),
        sa.Column(
            "dhan_segment",
            sa.String(length=16),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("dhan_underlying_symbol", sa.String(length=128), nullable=False),
        sa.Column("dhan_symbol_name", sa.Text(), nullable=True),
        sa.Column("dhan_display_name", sa.Text(), nullable=True),
        sa.Column("yahoo_symbol", sa.String(length=64), nullable=False),
        sa.Column("mapping_source", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dhan_exch_id",
            "dhan_segment",
            "dhan_underlying_symbol",
            name="uq_dhan_yahoo_dhan_symbol_exch_seg",
        ),
        sa.UniqueConstraint("dhan_security_id", name="uq_dhan_yahoo_dhan_security_id"),
    )
    op.create_index(
        op.f("ix_dhan_yahoo_instrument_map_isin"),
        "dhan_yahoo_instrument_map",
        ["isin"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dhan_yahoo_instrument_map_dhan_exch_id"),
        "dhan_yahoo_instrument_map",
        ["dhan_exch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dhan_yahoo_instrument_map_dhan_underlying_symbol"),
        "dhan_yahoo_instrument_map",
        ["dhan_underlying_symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dhan_yahoo_instrument_map_yahoo_symbol"),
        "dhan_yahoo_instrument_map",
        ["yahoo_symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dhan_yahoo_instrument_map_yahoo_symbol"),
        table_name="dhan_yahoo_instrument_map",
    )
    op.drop_index(
        op.f("ix_dhan_yahoo_instrument_map_dhan_underlying_symbol"),
        table_name="dhan_yahoo_instrument_map",
    )
    op.drop_index(
        op.f("ix_dhan_yahoo_instrument_map_dhan_exch_id"),
        table_name="dhan_yahoo_instrument_map",
    )
    op.drop_index(
        op.f("ix_dhan_yahoo_instrument_map_isin"),
        table_name="dhan_yahoo_instrument_map",
    )
    op.drop_table("dhan_yahoo_instrument_map")
