"""create_currency_list_mapper

Revision ID: 48cc29ddb6f6
Revises: 850a0dc437ca
Create Date: 2026-04-05 22:54:31.357171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48cc29ddb6f6'
down_revision: Union[str, Sequence[str], None] = '850a0dc437ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "currency_list_mapper",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("currency_name", sa.String(100), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("currency_code", name="uq_currency_list_mapper_currency_code"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("currency_list_mapper")
