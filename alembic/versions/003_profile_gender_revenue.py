"""profile gender, revenue table

Revision ID: 003
Revises: 002
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("gender", sa.String(16), nullable=True))
    op.create_table(
        "revenue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_revenue_period_date"), "revenue", ["period_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_revenue_period_date"), table_name="revenue")
    op.drop_table("revenue")
    op.drop_column("profiles", "gender")
