"""research custdev tables

Revision ID: 022
Revises: 021
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_interviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("thank_you_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_interviews_slug", "research_interviews", ["slug"], unique=True)

    op.create_table(
        "research_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["research_interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_questions_interview_id", "research_questions", ["interview_id"], unique=False)

    op.create_table(
        "research_response_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("public_token", sa.String(length=64), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["research_interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_response_sessions_interview_id", "research_response_sessions", ["interview_id"], unique=False)
    op.create_index("ix_research_response_sessions_public_token", "research_response_sessions", ["public_token"], unique=False)
    op.create_index("ix_research_response_sessions_completed_at", "research_response_sessions", ["completed_at"], unique=False)

    op.create_table(
        "research_answers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["research_response_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["research_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_answers_session_id", "research_answers", ["session_id"], unique=False)
    op.create_index("ix_research_answers_question_id", "research_answers", ["question_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_research_answers_question_id", table_name="research_answers")
    op.drop_index("ix_research_answers_session_id", table_name="research_answers")
    op.drop_table("research_answers")

    op.drop_index("ix_research_response_sessions_completed_at", table_name="research_response_sessions")
    op.drop_index("ix_research_response_sessions_public_token", table_name="research_response_sessions")
    op.drop_index("ix_research_response_sessions_interview_id", table_name="research_response_sessions")
    op.drop_table("research_response_sessions")

    op.drop_index("ix_research_questions_interview_id", table_name="research_questions")
    op.drop_table("research_questions")

    op.drop_index("ix_research_interviews_slug", table_name="research_interviews")
    op.drop_table("research_interviews")
