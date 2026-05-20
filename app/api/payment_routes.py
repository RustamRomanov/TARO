"""Оплата: подписка и пополнение баланса через ЮKassa."""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.core.config import get_settings
from app.core.security import get_telegram_user_from_init_data, get_telegram_user_id_from_init_data
from app.db.models import Payment, User
from app.db.session import get_db
from app.services.limits import _ensure_user
from app.services.cache import get_json as cache_get_json, set_json as cache_set_json
from app.services.subscription_expiry_notifications import run_subscription_expiry_notifications
from app.services.yookassa_service import (
    cancel_subscription_for_user,
    create_payment,
    process_webhook,
    reconcile_pending_payments,
    run_billing_cycle,
    verify_webhook_payment_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


def _subscription_status_cache_key(user_id: int) -> str:
    return f"payment_subscription_status:{user_id}"


def _payments_history_cache_key(user_id: int, limit: int) -> str:
    return f"payment_history:{user_id}:{limit}"


def _create_payment_idempotency_key(user_id: int, payment_type: str, amount_rub: float | None, return_url: str) -> str:
    raw = json.dumps(
        {
            "u": int(user_id),
            "t": (payment_type or "").strip().lower(),
            "a": float(amount_rub) if amount_rub is not None else None,
            "r": (return_url or "").strip(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"payment_create_idem:{digest}"


def _verify_billing_secret(request: Request) -> None:
    """Protect billing endpoints with mandatory secret in non-debug mode."""
    settings = get_settings()
    expected_secret = (settings.BILLING_CRON_SECRET or "").strip()
    if not expected_secret:
        if settings.DEBUG:
            return
        raise HTTPException(status_code=503, detail="Billing endpoints are not configured.")
    provided = (request.headers.get("X-Billing-Secret") or "").strip()
    if provided != expected_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


def _verify_yookassa_webhook_secret(request: Request) -> None:
    """Require shared webhook secret for YooKassa endpoint if configured.
    YooKassa по умолчанию не отправляет кастомные заголовки. Если YOOKASSA_WEBHOOK_SECRET
    не задан, проверка пропускается (безопасность через verify_webhook_payment_payload)."""
    expected = (get_settings().YOOKASSA_WEBHOOK_SECRET or "").strip()
    if not expected:
        return
    provided = (
        request.headers.get("X-YooKassa-Webhook-Secret")
        or request.headers.get("X-Webhook-Secret")
        or ""
    ).strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


class CreatePaymentRequest(BaseModel):
    init_data: str = ""
    payment_type: str = "subscription"
    amount_rub: float | None = None
    return_url: str = ""


class CancelSubscriptionRequest(BaseModel):
    init_data: str = ""


class ReconcilePendingRequest(BaseModel):
    limit: int = 200


class SubscriptionExpiryNotifyRequest(BaseModel):
    limit: int = 500


class ReferralInitBody(BaseModel):
    init_data: str = ""


@router.post("/referral/claim")
async def referral_claim(payload: ReferralInitBody, db=Depends(get_db)):
    """Привязать реферера из Redis (после перехода по ссылке /start ref_ в боте)."""
    telegram_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    from app.services.referral import claim_pending_referrer

    result = await claim_pending_referrer(db, telegram_id)
    await db.commit()
    return result


@router.post("/referral/info")
async def referral_info(payload: ReferralInitBody, db=Depends(get_db)):
    """Реферальная ссылка и параметры программы."""
    telegram_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    await _ensure_user(db, telegram_id)
    r = await db.execute(select(User).where(User.telegram_id == telegram_id).limit(1))
    user = r.scalar_one_or_none()
    settings = get_settings()
    bot = (getattr(settings, "TELEGRAM_BOT_USERNAME", None) or "").strip().lstrip("@")
    link = ""
    if bot:
        link = f"https://t.me/{bot}?start=ref_{telegram_id}"
    return {
        "referral_link": link,
        "percent": 50,
        "has_referrer": bool(getattr(user, "referred_by_telegram_id", None) if user else False),
    }


@router.post("/create")
async def payments_create(
    payload: CreatePaymentRequest,
    request: Request,
    db=Depends(get_db),
):
    """Создать платёж (подписка или пополнение). Возвращает confirmation_url для редиректа."""
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    user_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")

    user = await _ensure_user(db, user_id, username=username, full_name=full_name)

    idem_key = _create_payment_idempotency_key(
        user_id=user_id,
        payment_type=payload.payment_type,
        amount_rub=payload.amount_rub,
        return_url=(payload.return_url or "").strip(),
    )
    idem_cached = await cache_get_json(idem_key)
    if isinstance(idem_cached, dict) and isinstance(idem_cached.get("yookassa_payment_id"), str):
        return idem_cached

    result = await create_payment(
        db,
        user_id=user_id,
        payment_type=payload.payment_type,
        amount_rub=payload.amount_rub,
        return_url=(payload.return_url or "").strip(),
        user_obj=user,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    await db.commit()
    await cache_set_json(idem_key, result, ttl_seconds=25)
    return result


@router.post("/subscription/cancel")
async def subscription_cancel(
    payload: CancelSubscriptionRequest,
    db=Depends(get_db),
):
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    result = await cancel_subscription_for_user(db, user_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Не удалось отменить подписку."))
    await db.commit()
    return {"ok": True}


@router.get("/subscription/status")
async def subscription_status(init_data: str, db=Depends(get_db)):
    user_id = get_telegram_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    cache_key = _subscription_status_cache_key(user_id)
    cached = await cache_get_json(cache_key)
    if isinstance(cached, dict) and cached.get("status") is not None:
        return cached
    user = (
        await db.execute(select(User).where(User.telegram_id == user_id).limit(1))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    payload = {
        "status": user.status,
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "subscription_end_date": user.subscription_end_date.isoformat() if user.subscription_end_date else None,
        "subscription_next_charge_at": (
            user.subscription_next_charge_at.isoformat() if user.subscription_next_charge_at else None
        ),
        "subscription_canceled_at": (
            user.subscription_canceled_at.isoformat() if user.subscription_canceled_at else None
        ),
    }
    await cache_set_json(cache_key, payload, ttl_seconds=2)
    return payload


@router.post("/billing/run")
async def billing_run(request: Request, db=Depends(get_db)):
    """
    Cron endpoint: запускает цикл автопродлений.
    Защита: заголовок X-Billing-Secret должен совпадать с BILLING_CRON_SECRET.
    """
    _verify_billing_secret(request)
    result = await run_billing_cycle(db)
    await db.commit()
    return {"ok": True, **result}


@router.post("/billing/reconcile-pending")
async def billing_reconcile_pending(
    payload: ReconcilePendingRequest,
    request: Request,
    db=Depends(get_db),
):
    """Cron endpoint: reconcile local pending payments against YooKassa statuses."""
    _verify_billing_secret(request)
    result = await reconcile_pending_payments(db, limit_rows=max(1, min(int(payload.limit), 1000)))
    await db.commit()
    return result


@router.post("/billing/subscription-expiry-notify")
async def billing_subscription_expiry_notify(
    payload: SubscriptionExpiryNotifyRequest,
    request: Request,
    db=Depends(get_db),
):
    """
    Cron: напоминания в Telegram за 7/3/2/1 день до окончания Тарифа VIP.
    Отправка происходит только в окно 20:00-20:14 по Москве.
    Заголовок X-Billing-Secret.
    """
    _verify_billing_secret(request)
    result = await run_subscription_expiry_notifications(db, limit_users=payload.limit)
    await db.commit()
    return result


@router.get("/history")
async def payments_history(
    init_data: str,
    limit: int = 30,
    db=Depends(get_db),
):
    """История финансовых операций пользователя (подписки, пополнения, списания)."""
    user_id = get_telegram_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    limit = max(1, min(int(limit), 100))
    cache_key = _payments_history_cache_key(user_id, limit)
    cached = await cache_get_json(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return cached
    rows = (
        await db.execute(
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(desc(Payment.created_at))
            .limit(limit)
        )
    ).scalars().all()
    payload = {
        "items": [
            {
                "id": row.id,
                "kind": row.kind,
                "status": row.status,
                "amount_cents": row.amount_cents,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "yookassa_payment_id": row.yookassa_payment_id,
            }
            for row in rows
        ]
    }
    await cache_set_json(cache_key, payload, ttl_seconds=3)
    return payload


@router.get("/status/{yookassa_payment_id}")
async def payment_status(yookassa_payment_id: str, init_data: str, db=Depends(get_db)):
    """Быстрая проверка статуса конкретного платежа текущего пользователя."""
    user_id = get_telegram_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    cache_key = f"payment_status:{user_id}:{yookassa_payment_id}"
    cached = await cache_get_json(cache_key)
    if isinstance(cached, dict) and cached.get("yookassa_payment_id") == yookassa_payment_id:
        return cached
    row = (
        await db.execute(
            select(Payment).where(
                Payment.user_id == user_id,
                Payment.yookassa_payment_id == yookassa_payment_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Платеж не найден.")
    payload = {
        "id": row.id,
        "yookassa_payment_id": row.yookassa_payment_id,
        "kind": row.kind,
        "status": row.status,
        "amount_cents": row.amount_cents,
    }
    # High-frequency client polling benefits from short cache.
    await cache_set_json(cache_key, payload, ttl_seconds=2)
    return payload


@router.get("/success")
async def payment_success():
    """Страница после возврата с ЮKassa (return_url). Для Mini App можно отдать HTML с закрытием или редиректом."""
    return {"ok": True, "message": "Оплата принята в обработку. Если списание прошло - доступ обновится в течение минуты."}


@router.post("/webhook")
async def payments_webhook(request: Request, db=Depends(get_db)):
    """Webhook от ЮKassa. Проверяется shared secret + сверка payload с YooKassa API."""
    _verify_yookassa_webhook_secret(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    verified = await verify_webhook_payment_payload(body)
    if not verified:
        raise HTTPException(status_code=403, detail="Webhook payload verification failed.")
    ok = await process_webhook(db, body)
    await db.commit()
    return {"ok": ok}
