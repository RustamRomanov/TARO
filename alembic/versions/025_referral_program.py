"""Referral program: referred_by on users, referral_source_payment_id on payments

Revision ID: 025_referral
Revises: 024_sub_expiry
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa


revision = "025_referral"
down_revision = "024_sub_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referred_by_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_referred_by_telegram_id",
        "users",
        "users",
        ["referred_by_telegram_id"],
        ["telegram_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_users_referred_by_telegram_id",
        "users",
        ["referred_by_telegram_id"],
        unique=False,
    )
    op.add_column(
        "payments",
        sa.Column("referral_source_payment_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_referral_source_payment_id",
        "payments",
        "payments",
        ["referral_source_payment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_payments_referral_source_payment_id",
        "payments",
        ["referral_source_payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_referral_source_payment_id", table_name="payments")
    op.drop_constraint("fk_payments_referral_source_payment_id", "payments", type_="foreignkey")
    op.drop_column("payments", "referral_source_payment_id")
    op.drop_index("ix_users_referred_by_telegram_id", table_name="users")
    op.drop_constraint("fk_users_referred_by_telegram_id", "users", type_="foreignkey")
    op.drop_column("users", "referred_by_telegram_id")
