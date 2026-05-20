"""vision analysis history tables

Revision ID: 007
Revises: 006
Create Date: 2026-02-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "face_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("face_shape", sa.String(length=64), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("interpretation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_face_analyses_user_profile", "face_analyses", ["user_id", "profile_id"], unique=False)
    op.create_index("ix_face_analyses_user_created", "face_analyses", ["user_id", "created_at"], unique=False)

    op.create_table(
        "palm_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("hand_type", sa.String(length=64), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("mounts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("signs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("interpretation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_palm_analyses_user_profile", "palm_analyses", ["user_id", "profile_id"], unique=False)
    op.create_index("ix_palm_analyses_user_created", "palm_analyses", ["user_id", "created_at"], unique=False)

    op.create_table(
        "compatibility_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("profile_id_1", sa.Integer(), nullable=True),
        sa.Column("profile_id_2", sa.Integer(), nullable=True),
        sa.Column("image1_url", sa.Text(), nullable=False),
        sa.Column("image2_url", sa.Text(), nullable=False),
        sa.Column("compatibility_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interpretation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id_1"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["profile_id_2"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compatibility_user_created", "compatibility_analyses", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_compatibility_user_created", table_name="compatibility_analyses")
    op.drop_table("compatibility_analyses")

    op.drop_index("ix_palm_analyses_user_created", table_name="palm_analyses")
    op.drop_index("ix_palm_analyses_user_profile", table_name="palm_analyses")
    op.drop_table("palm_analyses")

    op.drop_index("ix_face_analyses_user_created", table_name="face_analyses")
    op.drop_index("ix_face_analyses_user_profile", table_name="face_analyses")
    op.drop_table("face_analyses")
