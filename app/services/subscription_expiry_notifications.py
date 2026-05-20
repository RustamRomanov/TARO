"""Напоминания в Telegram за 7/3/2/1 день до окончания Тарифа VIP (в 20:00 по Москве)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.main import get_bot
from app.core.config import get_settings
from app.db.models import SubscriptionExpiryNotice, User
from app.services.limits import USER_STATUS_FULL_ACCESS

logger = logging.getLogger(__name__)

_SUB_EXPIRY_BUCKETS = frozenset((7, 3, 2, 1))
_NOTICE_TZ = ZoneInfo("Europe/Moscow")
_NOTICE_HOUR = 20
_NOTICE_MINUTE_FROM = 0
_NOTICE_MINUTE_TO = 14


def _days_word_ru(n: int) -> str:
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return "дней"
    n = n % 10
    if n == 1:
        return "день"
    if 2 <= n <= 4:
        return "дня"
    return "дней"


def _build_subscription_expiry_message(
    days_left: int,
    period_end: date,
    app_url: str,
) -> str:
    word = _days_word_ru(days_left)
    text = (
        f"✨ Напоминаем с заботой: Тариф VIP закончится через <b>{days_left}</b> {word} "
        f"(до {period_end.strftime('%d.%m.%Y')}).\n"
        "Чтобы безлимит не ушел в отпуск без тебя, продли доступ заранее."
    )
    if app_url:
        text += f'\n\n<a href="{app_url}">Продлить в ASTROV</a>'
    else:
        text += '\n\n<a href="https://t.me/astrov_bot">Продлить в боте ASTROV</a>'
    return text


def _is_dispatch_window(now_msk: datetime) -> bool:
    return (
        now_msk.hour == _NOTICE_HOUR
        and _NOTICE_MINUTE_FROM <= now_msk.minute <= _NOTICE_MINUTE_TO
    )


async def try_send_subscription_expiry_telegram_for_user(
    db: AsyncSession,
    user: User,
    *,
    enforce_schedule_window: bool = True,
) -> bool:
    """
    Если оплаченный период Тарифа VIP активен, до конца периода ровно 1/2/3/7 календарных дней
    и запись об отправке ещё не создана, отправить одно сообщение в личку бота.
    """
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        return False
    bot = get_bot()
    if not bot:
        return False

    if (user.status or "").strip().lower() != USER_STATUS_FULL_ACCESS:
        return False
    sub = user.subscription_end_date
    if sub is None:
        return False

    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(_NOTICE_TZ)
    if enforce_schedule_window and not _is_dispatch_window(now_msk):
        return False
    today_msk: date = now_msk.date()
    end = sub.replace(tzinfo=timezone.utc) if sub.tzinfo is None else sub
    if end <= now_utc:
        return False

    period_end = end.astimezone(_NOTICE_TZ).date()
    days_left = (period_end - today_msk).days
    if days_left not in _SUB_EXPIRY_BUCKETS:
        return False

    bucket = str(days_left)
    existing = (
        await db.execute(
            select(SubscriptionExpiryNotice.id).where(
                SubscriptionExpiryNotice.user_id == user.telegram_id,
                SubscriptionExpiryNotice.period_end == period_end,
                SubscriptionExpiryNotice.bucket == bucket,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False

    app_url = (settings.APP_URL or "").strip().rstrip("/")
    text = _build_subscription_expiry_message(days_left, period_end, app_url)
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        db.add(
            SubscriptionExpiryNotice(
                user_id=user.telegram_id,
                period_end=period_end,
                bucket=bucket,
            )
        )
        await db.flush()
        return True
    except Exception:
        logger.exception("subscription_expiry_notice failed user_id=%s", user.telegram_id)
        return False


async def run_subscription_expiry_notifications(
    db: AsyncSession,
    *,
    limit_users: int = 500,
) -> dict[str, int | bool]:
    """
    Раз в сутки в 20:00 по Москве: пользователям с full_access и будущей subscription_end_date,
    у которых до конца периода ровно 7/3/2/1 календарных дней, отправить одно сообщение на каждую отметку.
    """
    limit_users = max(1, min(int(limit_users), 2000))
    if not get_settings().TELEGRAM_BOT_TOKEN or not get_bot():
        return {"ok": False, "error": "no_bot", "candidates": 0, "sent": 0, "skipped": 0}

    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(_NOTICE_TZ)
    if not _is_dispatch_window(now_msk):
        return {
            "ok": True,
            "scheduled_window": False,
            "timezone": "Europe/Moscow",
            "candidates": 0,
            "sent": 0,
            "skipped": 0,
        }
    today_msk: date = now_msk.date()
    rows = (
        await db.execute(
            select(User).where(
                User.subscription_end_date.is_not(None),
                User.subscription_end_date > now_utc,
                User.status == USER_STATUS_FULL_ACCESS,
            ).limit(limit_users)
        )
    ).scalars().all()

    sent = 0
    skipped = 0
    for user in rows:
        sub = user.subscription_end_date
        if sub is None:
            continue
        end = sub.replace(tzinfo=timezone.utc) if sub.tzinfo is None else sub
        days_left = (end.astimezone(_NOTICE_TZ).date() - today_msk).days
        if days_left not in _SUB_EXPIRY_BUCKETS:
            continue
        if await try_send_subscription_expiry_telegram_for_user(db, user):
            sent += 1
        else:
            skipped += 1

    return {
        "ok": True,
        "candidates": len(rows),
        "sent": sent,
        "skipped": skipped,
    }


async def notify_subscription_expiry_on_auth(db: AsyncSession, user: User) -> None:
    """При открытии приложения: та же логика, что у cron, но отправка только в окно 20:00-20:14 по Москве."""
    await try_send_subscription_expiry_telegram_for_user(db, user)
