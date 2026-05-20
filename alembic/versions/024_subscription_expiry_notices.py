"""subscription_expiry_notices for VIP expiry telegram reminders

Revision ID: 024_sub_expiry
Revises: 023
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


revision = "024_sub_expiry"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_expiry_notices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("bucket", sa.String(length=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "period_end",
            "bucket",
            name="uq_subscription_expiry_user_period_bucket",
        ),
    )
    op.create_index(
        "ix_subscription_expiry_notices_user_id",
        "subscription_expiry_notices",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_expiry_notices_user_id", table_name="subscription_expiry_notices")
    op.drop_table("subscription_expiry_notices")
