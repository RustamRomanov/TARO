"""numerology matrices and interpretations

Revision ID: 005
Revises: 004
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "numerology_matrices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("matrix_type", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_numerology_matrices_profile_id", "numerology_matrices", ["profile_id"], unique=False)
    op.create_index("ix_numerology_matrices_matrix_type", "numerology_matrices", ["matrix_type"], unique=False)
    op.create_index(
        "ix_numerology_matrices_profile_type",
        "numerology_matrices",
        ["profile_id", "matrix_type"],
        unique=False,
    )

    op.create_table(
        "numerology_interpretations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("matrix_id", sa.Integer(), nullable=True),
        sa.Column("interpretation_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["matrix_id"], ["numerology_matrices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_numerology_interpretations_matrix_id", "numerology_interpretations", ["matrix_id"], unique=False)
    op.create_index(
        "ix_numerology_interpretations_type",
        "numerology_interpretations",
        ["interpretation_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_numerology_interpretations_type", table_name="numerology_interpretations")
    op.drop_index("ix_numerology_interpretations_matrix_id", table_name="numerology_interpretations")
    op.drop_table("numerology_interpretations")

    op.drop_index("ix_numerology_matrices_profile_type", table_name="numerology_matrices")
    op.drop_index("ix_numerology_matrices_matrix_type", table_name="numerology_matrices")
    op.drop_index("ix_numerology_matrices_profile_id", table_name="numerology_matrices")
    op.drop_table("numerology_matrices")

