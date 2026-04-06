"""create_currency_exchange_rates

Revision ID: 850a0dc437ca
Revises: c4f2b1a8d3e0
Create Date: 2026-04-05 21:12:19.930442

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "850a0dc437ca"
down_revision: Union[str, Sequence[str], None] = "c4f2b1a8d3e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "currency_exchange_rates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rate_date",
            "base_currency",
            "quote_currency",
            name="uq_currency_exchange_rate_date_base_quote_currency",
        ),
    )
    op.create_index(
        "ix_currency_exchange_rates_rate_date",
        "currency_exchange_rates",
        ["rate_date"],
    )
    op.create_index(
        "ix_currency_exchange_rates_base_currency",
        "currency_exchange_rates",
        ["base_currency"],
    )
    op.create_index(
        "ix_currency_exchange_rates_quote_currency",
        "currency_exchange_rates",
        ["quote_currency"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_currency_exchange_rates_quote_currency",
        table_name="currency_exchange_rates",
    )
    op.drop_index(
        "ix_currency_exchange_rates_base_currency",
        table_name="currency_exchange_rates",
    )
    op.drop_index(
        "ix_currency_exchange_rates_rate_date",
        table_name="currency_exchange_rates",
    )
    op.drop_table("currency_exchange_rates")
