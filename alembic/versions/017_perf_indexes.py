"""add performance indexes

Revision ID: 017
Revises: 016
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_payments_user_created_at",
        "payments",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_payments_user_yookassa",
        "payments",
        ["user_id", "yookassa_payment_id"],
        unique=False,
    )
    op.create_index(
        "ix_history_user_type_request",
        "history",
        ["user_id", "type", "request_content"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_history_user_type_request", table_name="history")
    op.drop_index("ix_payments_user_yookassa", table_name="payments")
    op.drop_index("ix_payments_user_created_at", table_name="payments")

