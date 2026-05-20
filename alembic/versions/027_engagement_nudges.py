"""Engagement nudges delivery history

Revision ID: 027_engagement_nudges
Revises: 026_bot_chat
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa


revision = "027_engagement_nudges"
down_revision = "026_bot_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engagement_nudge_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("topic", sa.String(length=32), nullable=False),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("cta_text", sa.String(length=64), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("local_hour", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("last_seen_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_within_24h", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("blocked_within_24h", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_engagement_nudge_deliveries_user_id", "engagement_nudge_deliveries", ["user_id"], unique=False)
    op.create_index("ix_engagement_nudge_deliveries_topic", "engagement_nudge_deliveries", ["topic"], unique=False)
    op.create_index("ix_engagement_nudge_deliveries_template_key", "engagement_nudge_deliveries", ["template_key"], unique=False)
    op.create_index("ix_engagement_nudge_deliveries_sent_at", "engagement_nudge_deliveries", ["sent_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_engagement_nudge_deliveries_sent_at", table_name="engagement_nudge_deliveries")
    op.drop_index("ix_engagement_nudge_deliveries_template_key", table_name="engagement_nudge_deliveries")
    op.drop_index("ix_engagement_nudge_deliveries_topic", table_name="engagement_nudge_deliveries")
    op.drop_index("ix_engagement_nudge_deliveries_user_id", table_name="engagement_nudge_deliveries")
    op.drop_table("engagement_nudge_deliveries")
