"""balance_ledger table for FIFO tariff versioning

Revision ID: 012
Revises: 011
Create Date: 2026-02-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "balance_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("tariff_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_balance_ledger_user_id", "balance_ledger", ["user_id"], unique=False)
    op.create_index("ix_balance_ledger_payment_id", "balance_ledger", ["payment_id"], unique=False)

    # Backfill: one ledger entry per user with balance > 0 (tariff v1)
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "sqlite":
        conn.execute(
            sa.text(
                "INSERT INTO balance_ledger (user_id, amount_cents, tariff_version, created_at) "
                "SELECT telegram_id, balance_cents, 1, datetime('now') FROM users WHERE balance_cents > 0"
            )
        )
    else:
        conn.execute(
            sa.text(
                "INSERT INTO balance_ledger (user_id, amount_cents, tariff_version, created_at) "
                "SELECT telegram_id, balance_cents, 1, (NOW() AT TIME ZONE 'UTC') FROM users WHERE balance_cents > 0"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_balance_ledger_payment_id", table_name="balance_ledger")
    op.drop_index("ix_balance_ledger_user_id", table_name="balance_ledger")
    op.drop_table("balance_ledger")
