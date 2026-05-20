"""Учёт статуса «пользователь остановил / заблокировал бота» по обновлениям Telegram."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services.limits import _ensure_user

logger = logging.getLogger(__name__)

# Активный доступ к личному чату с ботом
_BOT_ACTIVE_STATUSES = frozenset({"member", "administrator", "creator"})
# Нет чата с ботом: заблокировал, удалил чат, вышел
_BOT_STOPPED_STATUSES = frozenset({"left", "kicked", "banned"})


async def record_bot_chat_member_status(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    new_status: str,
) -> None:
    """Сохранить статус из ChatMemberUpdated (приватный чат с ботом)."""
    raw = (new_status or "").strip().lower()
    if not raw:
        return
    await _ensure_user(session, telegram_id, username=username, full_name=full_name)
    now = datetime.now(timezone.utc)
    if raw in _BOT_STOPPED_STATUSES:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(bot_member_status=raw, bot_stopped_at=now)
        )
        logger.info("user %s bot chat status=%s (stopped)", telegram_id, raw)
    elif raw in _BOT_ACTIVE_STATUSES:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(bot_member_status=raw, bot_stopped_at=None)
        )
        logger.info("user %s bot chat status=%s (active)", telegram_id, raw)
    else:
        await session.execute(
            update(User).where(User.telegram_id == telegram_id).values(bot_member_status=raw)
        )


async def record_bot_unreachable_from_telegram_error(
    session: AsyncSession,
    *,
    telegram_id: int,
    error_message: str,
) -> None:
    """Если при отправке пришла ошибка «заблокировал», зафиксировать остановку."""
    msg = (error_message or "").lower()
    if "blocked" not in msg and "deactivated" not in msg and "bot was blocked" not in msg:
        return
    now = datetime.now(timezone.utc)
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(bot_member_status="kicked", bot_stopped_at=now)
    )
