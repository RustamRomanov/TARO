"""User: статус чата с ботом (блокировка / снова активен)

Revision ID: 026_bot_chat
Revises: 025_referral
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa


revision = "026_bot_chat"
down_revision = "025_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("bot_member_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("bot_stopped_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "bot_stopped_at")
    op.drop_column("users", "bot_member_status")
