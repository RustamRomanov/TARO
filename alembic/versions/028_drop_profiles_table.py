"""Drop profiles table (TARO: no natal profile)

Revision ID: 028_drop_profiles
Revises: 027_engagement_nudges
Create Date: 2026-05-20

"""
from alembic import op
import sqlalchemy as sa


revision = "028_drop_profiles"
down_revision = "027_engagement_nudges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tarot_readings") as batch_op:
            try:
                batch_op.drop_constraint(
                    "FOREIGN KEY(profile_id) REFERENCES profiles (id) ON DELETE SET NULL",
                    type_="foreignkey",
                )
            except Exception:
                pass
    else:
        op.drop_constraint(
            "tarot_readings_profile_id_fkey",
            "tarot_readings",
            type_="foreignkey",
        )
    op.drop_index("ix_tarot_readings_user_profile_created", table_name="tarot_readings")
    op.drop_constraint("uq_profiles_user_id", "profiles", type_="unique")
    op.drop_table("profiles")


def downgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("gender", sa.String(length=16), nullable=True),
        sa.Column("gender_source", sa.String(length=16), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("birth_time", sa.String(length=16), nullable=True),
        sa.Column("birth_city", sa.String(length=255), nullable=True),
        sa.Column("birth_lat", sa.Float(), nullable=True),
        sa.Column("birth_lon", sa.Float(), nullable=True),
        sa.Column("relationship_status", sa.String(length=32), nullable=True),
        sa.Column("occupation", sa.String(length=32), nullable=True),
        sa.Column("interests", sa.JSON(), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_tarot_readings_user_profile_created",
        "tarot_readings",
        ["user_id", "profile_id", "created_at"],
        unique=False,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("tarot_readings") as batch_op:
            batch_op.create_foreign_key(
                "fk_tarot_readings_profile_id",
                "profiles",
                ["profile_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "tarot_readings_profile_id_fkey",
            "tarot_readings",
            "profiles",
            ["profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
