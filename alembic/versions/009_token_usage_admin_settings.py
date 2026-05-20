"""token_usage and admin_settings

Revision ID: 009
Revises: 008
Create Date: 2026-02-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "token_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("feature_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cost_rub", sa.Float(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.telegram_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_usage_user_id", "token_usage", ["user_id"], unique=False)
    op.create_index("ix_token_usage_created_at", "token_usage", ["created_at"], unique=False)
    op.create_index("ix_token_usage_feature", "token_usage", ["feature_type"], unique=False)
    op.create_index("ix_token_usage_provider", "token_usage", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_token_usage_provider", table_name="token_usage")
    op.drop_index("ix_token_usage_feature", table_name="token_usage")
    op.drop_index("ix_token_usage_created_at", table_name="token_usage")
    op.drop_index("ix_token_usage_user_id", table_name="token_usage")
    op.drop_table("token_usage")
    op.drop_table("admin_settings")
