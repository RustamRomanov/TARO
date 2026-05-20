"""profile avatar_url

Revision ID: 015
Revises: 014
Create Date: 2026-02-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("avatar_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "avatar_url")
