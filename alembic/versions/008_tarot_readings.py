"""tarot readings with chat history

Revision ID: 008
Revises: 007
Create Date: 2026-02-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tarot_readings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("spread_code", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False, server_default=""),
        sa.Column("cards", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "cards_interpretations", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("question_essence", sa.Text(), nullable=False, server_default=""),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("advice", sa.Text(), nullable=False, server_default=""),
        sa.Column("chat_history", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tarot_readings_user_created", "tarot_readings", ["user_id", "created_at"], unique=False)
    op.create_index(
        "ix_tarot_readings_user_profile_created",
        "tarot_readings",
        ["user_id", "profile_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_tarot_readings_user_spread", "tarot_readings", ["user_id", "spread_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tarot_readings_user_spread", table_name="tarot_readings")
    op.drop_index("ix_tarot_readings_user_profile_created", table_name="tarot_readings")
    op.drop_index("ix_tarot_readings_user_created", table_name="tarot_readings")
    op.drop_table("tarot_readings")
