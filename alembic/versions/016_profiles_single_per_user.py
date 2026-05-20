"""enforce single profile per user

Revision ID: 016
Revises: 015
Create Date: 2026-02-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_value(raw: str | None) -> bool:
    return bool((raw or "").strip())


def _priority_key(row: dict) -> tuple[int, int, int, int, int, int, int]:
    return (
        1 if row.get("birth_date") is not None else 0,
        1 if _has_value(row.get("birth_city")) else 0,
        1 if _has_value(row.get("name")) else 0,
        1 if _has_value(row.get("gender")) else 0,
        1 if _has_value(row.get("avatar_url")) else 0,
        1 if bool(row.get("is_primary")) else 0,
        int(row.get("id") or 0),
    )


def _merge_missing(target: dict, source: dict) -> None:
    if not _has_value(target.get("name")) and _has_value(source.get("name")):
        target["name"] = source.get("name")
    if target.get("birth_date") is None and source.get("birth_date") is not None:
        target["birth_date"] = source.get("birth_date")
    if not _has_value(target.get("birth_time")) and _has_value(source.get("birth_time")):
        target["birth_time"] = source.get("birth_time")
    if not _has_value(target.get("birth_city")) and _has_value(source.get("birth_city")):
        target["birth_city"] = source.get("birth_city")
    if not _has_value(target.get("gender")) and _has_value(source.get("gender")):
        target["gender"] = source.get("gender")
    if not _has_value(target.get("avatar_url")) and _has_value(source.get("avatar_url")):
        target["avatar_url"] = source.get("avatar_url")


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, name, gender, birth_date, birth_time, birth_city, avatar_url, is_primary
            FROM profiles
            ORDER BY user_id ASC, id ASC
            """
        )
    ).mappings().all()

    by_user: dict[int, list[dict]] = {}
    for row in rows:
        uid = int(row["user_id"])
        by_user.setdefault(uid, []).append(dict(row))

    for user_id, profiles in by_user.items():
        if len(profiles) <= 1:
            if len(profiles) == 1 and not profiles[0].get("is_primary"):
                bind.execute(
                    sa.text("UPDATE profiles SET is_primary = true WHERE id = :id"),
                    {"id": int(profiles[0]["id"])},
                )
            continue

        canonical = max(profiles, key=_priority_key)
        for p in profiles:
            if int(p["id"]) == int(canonical["id"]):
                continue
            _merge_missing(canonical, p)

        bind.execute(
            sa.text(
                """
                UPDATE profiles
                SET name = :name,
                    gender = :gender,
                    birth_date = :birth_date,
                    birth_time = :birth_time,
                    birth_city = :birth_city,
                    avatar_url = :avatar_url,
                    is_primary = true
                WHERE id = :id
                """
            ),
            {
                "id": int(canonical["id"]),
                "name": canonical.get("name"),
                "gender": canonical.get("gender"),
                "birth_date": canonical.get("birth_date"),
                "birth_time": canonical.get("birth_time"),
                "birth_city": canonical.get("birth_city"),
                "avatar_url": canonical.get("avatar_url"),
            },
        )

        bind.execute(
            sa.text(
                """
                DELETE FROM profiles
                WHERE user_id = :user_id AND id <> :canonical_id
                """
            ),
            {"user_id": user_id, "canonical_id": int(canonical["id"])},
        )

    op.create_unique_constraint("uq_profiles_user_id", "profiles", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_profiles_user_id", "profiles", type_="unique")
