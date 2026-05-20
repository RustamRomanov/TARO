"""subscription recurring fields

Revision ID: 011
Revises: 010
Create Date: 2026-02-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("subscription_next_charge_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("subscription_canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("subscription_payment_method_id", sa.String(length=128), nullable=True))
    op.create_index("ix_users_subscription_next_charge_at", "users", ["subscription_next_charge_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_subscription_next_charge_at", table_name="users")
    op.drop_column("users", "subscription_payment_method_id")
    op.drop_column("users", "subscription_canceled_at")
    op.drop_column("users", "subscription_next_charge_at")
