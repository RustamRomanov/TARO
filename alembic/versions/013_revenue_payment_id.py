"""revenue payment_id for backfill deduplication

Revision ID: 013
Revises: 012
Create Date: 2026-02-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("revenue", sa.Column("payment_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_revenue_payment_id",
        "revenue",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_revenue_payment_id", "revenue", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revenue_payment_id", table_name="revenue")
    op.drop_constraint("fk_revenue_payment_id", "revenue", type_="foreignkey")
    op.drop_column("revenue", "payment_id")
