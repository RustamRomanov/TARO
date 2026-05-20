"""profile optional fields and horoscope history

Revision ID: 021
Revises: 020
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("relationship_status", sa.String(length=32), nullable=True))
    op.add_column("profiles", sa.Column("occupation", sa.String(length=32), nullable=True))
    op.add_column("profiles", sa.Column("interests", sa.JSON(), nullable=True))

    op.create_table(
        "horoscope_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("blocks_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", "period", name="uq_horoscope_history_user_date_period"),
    )
    op.create_index("ix_horoscope_history_user_created_at", "horoscope_history", ["user_id", "created_at"], unique=False)
    op.create_index("ix_horoscope_history_date_period", "horoscope_history", ["date", "period"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_horoscope_history_date_period", table_name="horoscope_history")
    op.drop_index("ix_horoscope_history_user_created_at", table_name="horoscope_history")
    op.drop_table("horoscope_history")

    op.drop_column("profiles", "interests")
    op.drop_column("profiles", "occupation")
    op.drop_column("profiles", "relationship_status")
