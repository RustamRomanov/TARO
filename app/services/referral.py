"""Реферальная программа: приглашение по ссылке, бонус 50% от оплат приглашённого."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, User
from app.services.cache import delete_json, get_json, set_json
from app.services.limits import _ensure_user, add_balance_ledger_on_topup

logger = logging.getLogger(__name__)

REFERRAL_PENDING_KEY = "referral_pending:{telegram_id}"
REFERRAL_PERCENT = 50
REFERRAL_PENDING_TTL_SECONDS = 14 * 86400

# Типы платежей ЮKassa, от которых начисляется бонус рефереру (совпадает с учётом дохода).
REFERRAL_ELIGIBLE_PAYMENT_TYPES: frozenset[str] = frozenset(
    {
        "topup",
        "subscription",
        "subscription_renewal",
        "vip_10d",
        "vip_30d",
        "vip_100d",
        "vip_1m",
        "vip_3m",
        "vip_6m",
    }
)


async def store_pending_referrer(invitee_telegram_id: int, referrer_telegram_id: int) -> None:
    """Сохранить ожидающего реферера после /start ref_ в боте."""
    if invitee_telegram_id == referrer_telegram_id:
        return
    if referrer_telegram_id <= 0:
        return
    key = REFERRAL_PENDING_KEY.format(telegram_id=invitee_telegram_id)
    await set_json(
        key,
        {"referrer_telegram_id": int(referrer_telegram_id)},
        ttl_seconds=REFERRAL_PENDING_TTL_SECONDS,
    )


async def claim_pending_referrer(db: AsyncSession, invitee_telegram_id: int) -> dict[str, Any]:
    """
    Привязать реферера из Redis к пользователю один раз.
    Вызывать после авторизации в Mini App.
    """
    await _ensure_user(db, invitee_telegram_id)
    result = await db.execute(select(User).where(User.telegram_id == invitee_telegram_id).limit(1))
    user = result.scalar_one_or_none()
    if not user:
        return {"ok": False, "claimed": False, "reason": "no_user"}

    if getattr(user, "referred_by_telegram_id", None):
        return {"ok": True, "claimed": False, "reason": "already_bound"}

    key = REFERRAL_PENDING_KEY.format(telegram_id=invitee_telegram_id)
    pending = await get_json(key)
    if not isinstance(pending, dict):
        return {"ok": True, "claimed": False, "reason": "no_pending"}

    ref_id = int(pending.get("referrer_telegram_id") or 0)
    await delete_json(key)

    if ref_id <= 0 or ref_id == invitee_telegram_id:
        return {"ok": True, "claimed": False, "reason": "invalid_ref"}

    ref_result = await db.execute(select(User).where(User.telegram_id == ref_id).limit(1))
    if ref_result.scalar_one_or_none() is None:
        return {"ok": True, "claimed": False, "reason": "referrer_not_found"}

    user.referred_by_telegram_id = ref_id
    await db.flush()
    return {"ok": True, "claimed": True, "referrer_telegram_id": ref_id}


async def process_referral_bonus_for_successful_payment(
    db: AsyncSession,
    *,
    payer_telegram_id: int,
    payment_row: Payment,
    payment_type: str,
    amount_cents: int,
) -> None:
    """После успешной оплаты приглашённого: 50% бонусом на баланс реферера."""
    pt = (payment_type or "").strip()
    if pt not in REFERRAL_ELIGIBLE_PAYMENT_TYPES:
        return
    if amount_cents <= 0:
        return

    existing = await db.execute(
        select(Payment.id).where(
            Payment.kind == "referral_bonus",
            Payment.referral_source_payment_id == payment_row.id,
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return

    payer = await db.get(User, payer_telegram_id)
    if not payer:
        return

    ref = getattr(payer, "referred_by_telegram_id", None)
    if not ref or int(ref) == int(payer_telegram_id):
        return

    referrer = await db.get(User, int(ref))
    if not referrer:
        return

    bonus = int(amount_cents * REFERRAL_PERCENT // 100)
    if bonus < 1:
        return

    referrer.balance_cents = (getattr(referrer, "balance_cents", 0) or 0) + bonus
    meta = {
        "invited_telegram_id": payer_telegram_id,
        "source_payment_id": payment_row.id,
        "source_kind": pt,
        "percent": REFERRAL_PERCENT,
        "note": "referral_bonus",
    }
    bonus_payment = Payment(
        user_id=int(ref),
        amount_cents=bonus,
        kind="referral_bonus",
        status="succeeded",
        referral_source_payment_id=payment_row.id,
        metadata_json=json.dumps(meta, ensure_ascii=False),
    )
    db.add(bonus_payment)
    await db.flush()
    await add_balance_ledger_on_topup(db, int(ref), bonus, payment_id=bonus_payment.id)
    logger.info(
        "Referral bonus: referrer=%s +%s kopeks from payment %s (invitee=%s)",
        ref,
        bonus,
        payment_row.id,
        payer_telegram_id,
    )
