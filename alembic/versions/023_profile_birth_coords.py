"""profiles birth_lat birth_lon

Revision ID: 023
Revises: 022
Create Date: 2026-03-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("birth_lat", sa.Float(), nullable=True))
    op.add_column("profiles", sa.Column("birth_lon", sa.Float(), nullable=True))

    bind = op.get_bind()
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from sqlalchemy import text

        from app.services.astrology import resolve_city_coordinates

        result = bind.execute(
            text("SELECT id, birth_city FROM profiles WHERE birth_city IS NOT NULL AND TRIM(birth_city) <> ''")
        )
        rows = result.fetchall()
        for row in rows:
            pid = row[0]
            bc = row[1]
            if not bc or not str(bc).strip():
                continue
            coords = resolve_city_coordinates(str(bc).strip())
            if not coords:
                continue
            la, lo = float(coords[0]), float(coords[1])
            bind.execute(
                text("UPDATE profiles SET birth_lat = :la, birth_lon = :lo WHERE id = :id"),
                {"la": la, "lo": lo, "id": pid},
            )
    except Exception:
        # Колонки добавлены; при ошибке бэкапа координаты подтянутся при следующем sync профиля.
        pass


def downgrade() -> None:
    op.drop_column("profiles", "birth_lon")
    op.drop_column("profiles", "birth_lat")
