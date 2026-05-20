"""history tokens/cost, users subscription_end_date, feedback table

Revision ID: 002
Revises: 001
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("history", sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("history", sa.Column("cost_estimate", sa.Float(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("subscription_end_date", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feedback_user_id"), "feedback", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_feedback_user_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_column("users", "subscription_end_date")
    op.drop_column("history", "cost_estimate")
    op.drop_column("history", "tokens_used")
