"""expenses table for cost tracking (commission, advertising, taxes, tokens)

Revision ID: 004
Revises: 003
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expenses_period_date"), "expenses", ["period_date"], unique=False)
    op.create_index(op.f("ix_expenses_category"), "expenses", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_expenses_category"), table_name="expenses")
    op.drop_index(op.f("ix_expenses_period_date"), table_name="expenses")
    op.drop_table("expenses")
