"""user payment methods table for recurring billing

Revision ID: 014
Revises: 013
Create Date: 2026-02-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="yookassa"),
        sa.Column("payment_method_id", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "payment_method_id",
            name="uq_user_payment_methods_user_provider_method",
        ),
    )
    op.create_index("ix_user_payment_methods_user_id", "user_payment_methods", ["user_id"], unique=False)
    op.create_index("ix_user_payment_methods_provider", "user_payment_methods", ["provider"], unique=False)
    op.create_index("ix_user_payment_methods_payment_method_id", "user_payment_methods", ["payment_method_id"], unique=False)
    op.create_index("ix_user_payment_methods_is_active", "user_payment_methods", ["is_active"], unique=False)
    op.create_index("ix_user_payment_methods_is_default", "user_payment_methods", ["is_default"], unique=False)

    # Backfill existing saved method from users.subscription_payment_method_id.
    op.execute(
        sa.text(
            """
            INSERT INTO user_payment_methods
                (user_id, provider, payment_method_id, is_active, is_default, metadata_json)
            SELECT
                telegram_id,
                'yookassa',
                subscription_payment_method_id,
                true,
                true,
                '{"source":"users.subscription_payment_method_id_backfill"}'
            FROM users
            WHERE subscription_payment_method_id IS NOT NULL
              AND subscription_payment_method_id <> ''
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_payment_methods_is_default", table_name="user_payment_methods")
    op.drop_index("ix_user_payment_methods_is_active", table_name="user_payment_methods")
    op.drop_index("ix_user_payment_methods_payment_method_id", table_name="user_payment_methods")
    op.drop_index("ix_user_payment_methods_provider", table_name="user_payment_methods")
    op.drop_index("ix_user_payment_methods_user_id", table_name="user_payment_methods")
    op.drop_table("user_payment_methods")
