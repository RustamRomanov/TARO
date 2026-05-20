"""users, profiles, history tables (Full Access)

Revision ID: 001
Revises:
Create Date: 2025-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="free"),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_trial_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("daily_tarot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_vision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_dreams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reset_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("telegram_id"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("birth_time", sa.String(16), nullable=True),
        sa.Column("birth_city", sa.String(255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_profiles_user_id"), "profiles", ["user_id"], unique=False)
    op.create_table(
        "history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("request_content", sa.Text(), nullable=True),
        sa.Column("response_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_history_user_id"), "history", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_history_user_id"), table_name="history")
    op.drop_table("history")
    op.drop_index(op.f("ix_profiles_user_id"), table_name="profiles")
    op.drop_table("profiles")
    op.drop_table("users")
