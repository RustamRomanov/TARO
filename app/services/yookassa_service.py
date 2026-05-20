"""ЮKassa: платежи, пробный период, автопродление подписки."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Expense, Payment, Revenue, User, UserPaymentMethod
from app.services.limits import add_balance_ledger_on_topup
from app.services.referral import process_referral_bonus_for_successful_payment

logger = logging.getLogger(__name__)

SUBSCRIPTION_PRICE_RUB = 399
SUBSCRIPTION_MONTHS = 1
TRIAL_DAYS = 3
TOPUP_ALLOWED_RUB = {50, 100, 200}

# Тариф VIP — разовая покупка на срок в днях (без рекуррента).
# Ниже legacy-ключи (vip_1m и др.): только для уже созданных платежей; новые покупки идут через vip_10d / vip_30d / vip_100d.
VIP_TARIFFS: dict[str, tuple[float, int]] = {
    "vip_10d": (199.0, 10),
    "vip_30d": (399.0, 30),
    "vip_100d": (999.0, 100),
    "vip_1m": (399.0, 31),
    "vip_3m": (999.0, 93),
    "vip_6m": (1499.0, 186),
}


def _vip_period_days_word(days: int) -> str:
    """Склонение для чека: «на N дней/дня/день»."""
    n = abs(int(days)) % 100
    n1 = n % 10
    if 11 <= n <= 14:
        return "дней"
    if n1 == 1:
        return "день"
    if 2 <= n1 <= 4:
        return "дня"
    return "дней"
RECURRING_FORBIDDEN_MARKERS = (
    "can't make recurring payments",
    "recurring payments",
    "save_payment_method",
)
YOOKASSA_SYNC_CALL_TIMEOUT_SEC = 15.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _configure_yookassa() -> bool:
    settings = get_settings()
    if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
        logger.warning(
            "YooKassa is not configured: missing shop_id=%s secret=%s",
            bool(settings.YOOKASSA_SHOP_ID),
            bool(settings.YOOKASSA_SECRET_KEY),
        )
        return False
    try:
        from yookassa import Configuration
        Configuration.configure(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        return True
    except Exception as e:
        logger.warning("YooKassa configure failed: %s", e)
        return False


async def _run_yookassa_sync_call(func, *args, **kwargs):
    """Run blocking YooKassa SDK call outside event loop with timeout."""
    call = partial(func, *args, **kwargs)
    return await asyncio.wait_for(
        asyncio.to_thread(call),
        timeout=YOOKASSA_SYNC_CALL_TIMEOUT_SEC,
    )


def _extract_payment_method_id(obj: dict) -> str | None:
    pm = obj.get("payment_method") or {}
    value = str(pm.get("id") or "").strip()
    return value or None


def _extract_income_amount_rub(obj: dict) -> float | None:
    """Extract net amount (after YooKassa fee) from webhook payload."""
    try:
        raw = (obj.get("income_amount") or {}).get("value")
        if raw is None:
            return None
        return float(raw)
    except (TypeError, ValueError):
        return None


def _merge_payment_metadata(row: Payment, **extra: object) -> None:
    """Merge extra fields into payment metadata JSON safely."""
    current: dict = {}
    if row.metadata_json:
        try:
            parsed = json.loads(row.metadata_json)
            if isinstance(parsed, dict):
                current = parsed
        except (TypeError, json.JSONDecodeError):
            current = {}
    for k, v in extra.items():
        current[k] = v
    row.metadata_json = json.dumps(current, ensure_ascii=False)


def _build_receipt_email(user: User) -> str:
    """
    YooKassa receipts require customer email or phone.
    Build a stable synthetic email from APP_URL host + telegram id.
    """
    settings = get_settings()
    host = (urlparse((settings.APP_URL or "").strip()).hostname or "astrov.app").strip().lower()
    if not host:
        host = "astrov.app"
    local_part = f"user{int(user.telegram_id)}"
    return f"{local_part}@{host}"


def _build_receipt(*, user: User, description: str, amount_rub: float) -> dict:
    item_description = (description or "Оплата ASTROV").strip()
    if len(item_description) > 128:
        item_description = item_description[:125] + "..."
    value_str = f"{float(amount_rub):.2f}"
    return {
        "customer": {"email": _build_receipt_email(user)},
        "items": [
            {
                "description": item_description,
                "quantity": "1.00",
                "amount": {"value": value_str, "currency": "RUB"},
                "vat_code": 1,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }


async def _get_default_active_payment_method(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str = "yookassa",
) -> UserPaymentMethod | None:
    """Resolve the best active payment method for recurring charge."""
    row = (
        await db.execute(
            select(UserPaymentMethod)
            .where(
                UserPaymentMethod.user_id == user_id,
                UserPaymentMethod.provider == provider,
                UserPaymentMethod.is_active == True,  # noqa: E712
            )
            .order_by(UserPaymentMethod.is_default.desc(), UserPaymentMethod.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _upsert_user_payment_method(
    db: AsyncSession,
    *,
    user_id: int,
    payment_method_id: str,
    provider: str = "yookassa",
    set_default: bool = False,
    metadata: dict | None = None,
) -> UserPaymentMethod:
    """Store or reactivate saved payment method and optionally make it default."""
    existing = (
        await db.execute(
            select(UserPaymentMethod).where(
                UserPaymentMethod.user_id == user_id,
                UserPaymentMethod.provider == provider,
                UserPaymentMethod.payment_method_id == payment_method_id,
            ).limit(1)
        )
    ).scalar_one_or_none()

    if set_default:
        await db.execute(
            update(UserPaymentMethod)
            .where(
                UserPaymentMethod.user_id == user_id,
                UserPaymentMethod.provider == provider,
                UserPaymentMethod.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )

    if existing:
        existing.is_active = True
        existing.deactivated_at = None
        if set_default:
            existing.is_default = True
        if metadata:
            current = {}
            if existing.metadata_json:
                try:
                    parsed = json.loads(existing.metadata_json)
                    if isinstance(parsed, dict):
                        current = parsed
                except (TypeError, json.JSONDecodeError):
                    current = {}
            current.update(metadata)
            existing.metadata_json = json.dumps(current, ensure_ascii=False)
        await db.flush()
        return existing

    if not set_default:
        has_default = (
            await db.execute(
                select(UserPaymentMethod.id).where(
                    UserPaymentMethod.user_id == user_id,
                    UserPaymentMethod.provider == provider,
                    UserPaymentMethod.is_active == True,  # noqa: E712
                    UserPaymentMethod.is_default == True,  # noqa: E712
                ).limit(1)
            )
        ).scalar_one_or_none()
        set_default = has_default is None

    row = UserPaymentMethod(
        user_id=user_id,
        provider=provider,
        payment_method_id=payment_method_id,
        is_active=True,
        is_default=set_default,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(row)
    await db.flush()
    return row


async def _deactivate_user_payment_methods(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str = "yookassa",
) -> None:
    """Deactivate all stored methods for user/provider."""
    await db.execute(
        update(UserPaymentMethod)
        .where(
            UserPaymentMethod.user_id == user_id,
            UserPaymentMethod.provider == provider,
            UserPaymentMethod.is_active == True,  # noqa: E712
        )
        .values(
            is_active=False,
            is_default=False,
            deactivated_at=_utcnow(),
        )
    )
    await db.flush()


async def _create_payment_record(
    db: AsyncSession,
    *,
    user_id: int,
    yookassa_payment_id: str,
    amount_cents: int,
    kind: str,
    status: str,
    metadata: dict | None = None,
) -> Payment:
    row = Payment(
        user_id=user_id,
        yookassa_payment_id=yookassa_payment_id,
        amount_cents=amount_cents,
        kind=kind,
        status=status,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(row)
    await db.flush()
    return row


async def create_payment(
    db: AsyncSession,
    user_id: int,
    payment_type: str,
    amount_rub: Optional[float] = None,
    return_url: str = "",
    user_obj: User | None = None,
) -> dict:
    """
    payment_type:
    - subscription: первая подписка запускает trial 3 дня (capture=False, списание позже).
      Если trial уже был использован - списание сразу.
    - topup: пополнение баланса (50/100/200).
    """
    if not _configure_yookassa():
        return {
            "error": (
                "Оплата не настроена: проверьте YOOKASSA_SHOP_ID и "
                "YOOKASSA_SECRET_KEY в переменных окружения сервера."
            )
        }

    user = user_obj
    if user is None:
        user = (
            await db.execute(select(User).where(User.telegram_id == user_id).limit(1))
        ).scalar_one_or_none()
    if not user:
        return {"error": "Пользователь не найден."}

    if payment_type == "subscription":
        if get_settings().YOOKASSA_SBP_ONLY:
            return {"error": "Тариф VIP временно недоступен. Доступ только по балансу (СБП)."}
        amount_rub = float(SUBSCRIPTION_PRICE_RUB)
        use_trial = not bool(user.is_trial_used)
        capture_now = not use_trial
        description = (
            "Подписка ASTROV - 399 ₽/месяц, пробный период 3 дня"
            if use_trial
            else "Подписка ASTROV - 399 ₽/месяц"
        )
    elif payment_type in VIP_TARIFFS:
        amount_rub, days = VIP_TARIFFS[payment_type]
        capture_now = True
        use_trial = False
        dw = _vip_period_days_word(days)
        description = f"Тариф VIP ASTROV - {int(amount_rub)} ₽ на {days} {dw}"
    elif payment_type == "topup":
        if amount_rub is None:
            return {"error": "Укажите сумму пополнения."}
        amount_rub = round(float(amount_rub), 2)
        if int(amount_rub) != amount_rub or int(amount_rub) not in TOPUP_ALLOWED_RUB:
            return {"error": "Доступны пополнения только на 50, 100 или 200 ₽."}
        description = f"Пополнение баланса ASTROV - {amount_rub} ₽"
        use_trial = False
        capture_now = True
    else:
        return {"error": "Неверный тип платежа."}

    settings = get_settings()
    return_url = (return_url or settings.APP_URL or "").strip() or "https://t.me/astrov_bot"

    from yookassa import Payment as YooPayment
    plan_val = (
        "monthly_399_trial_3d" if payment_type == "subscription"
        else ("vip_tariff" if payment_type in VIP_TARIFFS else "balance_topup")
    )
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "description": description,
        "receipt": _build_receipt(user=user, description=description, amount_rub=float(amount_rub)),
        "metadata": {
            "user_id": str(user_id),
            "payment_type": payment_type,
            "plan": plan_val,
        },
        "capture": capture_now,
        "save_payment_method": payment_type == "subscription",
    }
    if payment_type in {"subscription", "topup"} or payment_type in VIP_TARIFFS:
        if get_settings().YOOKASSA_SBP_ONLY:
            payload["payment_method_data"] = {"type": "sbp"}
            payload["confirmation"] = {
                "type": "redirect",
                "return_url": return_url,
            }
        else:
            payload["confirmation"] = {
                "type": "embedded",
                "locale": "ru_RU",
            }

    recurring_fallback_used = False
    try:
        payment = await _run_yookassa_sync_call(YooPayment.create, payload)
    except Exception as e:
        error_text = str(e).lower()
        # Some YooKassa stores cannot use recurring/save_payment_method.
        # In that case we gracefully fallback to one-time subscription payment.
        if payment_type == "subscription" and any(marker in error_text for marker in RECURRING_FORBIDDEN_MARKERS):
            logger.warning(
                "YooKassa recurring unavailable for shop, fallback to one-time subscription for user=%s",
                user_id,
            )
            fallback_payload = dict(payload)
            fallback_payload["capture"] = True
            fallback_payload["save_payment_method"] = False
            fallback_payload["description"] = "Подписка ASTROV - 399 ₽/месяц (без автопродления)"
            fallback_payload["metadata"] = {
                **(payload.get("metadata") or {}),
                "plan": "monthly_399_manual_renewal",
                "recurring_fallback": "1",
            }
            try:
                payment = await _run_yookassa_sync_call(YooPayment.create, fallback_payload)
                recurring_fallback_used = True
                use_trial = False
                capture_now = True
                description = fallback_payload["description"]
            except Exception as fallback_exc:
                logger.exception("YooKassa fallback create failed: %s", fallback_exc)
                return {"error": "Не удалось создать платёж. Попробуйте позже."}
        else:
            logger.exception("YooKassa create failed: %s", e)
            return {"error": "Не удалось создать платёж. Попробуйте позже."}

    yookassa_id = payment.id
    confirmation_url = getattr(payment.confirmation, "confirmation_url", None) or getattr(payment, "confirmation_url", "") or ""
    confirmation_token = getattr(payment.confirmation, "confirmation_token", None) or ""
    amount_cents = int(round(float(amount_rub) * 100))

    await _create_payment_record(
        db,
        user_id=user_id,
        yookassa_payment_id=yookassa_id,
        amount_cents=amount_cents if (payment_type == "topup" or payment_type in VIP_TARIFFS) else 0,
        kind=payment_type,
        status="pending",
        metadata={
            "amount_rub": amount_rub,
            "description": description,
            "trial_mode": bool(use_trial) if payment_type == "subscription" else False,
            "capture_now": bool(capture_now),
            "recurring_fallback_used": recurring_fallback_used,
        },
    )

    return {
        "yookassa_payment_id": yookassa_id,
        "confirmation_url": confirmation_url,
        "confirmation_token": confirmation_token,
        "amount_rub": amount_rub,
        "amount_cents": amount_cents,
        "recurring_fallback_used": recurring_fallback_used,
    }


async def _create_recurring_charge(
    db: AsyncSession,
    *,
    user: User,
    kind: str = "subscription_renewal",
) -> bool:
    if not _configure_yookassa():
        return False
    method = await _get_default_active_payment_method(db, user_id=user.telegram_id, provider="yookassa")
    payment_method_id = (method.payment_method_id if method else "") or (user.subscription_payment_method_id or "")
    payment_method_id = payment_method_id.strip()
    if not payment_method_id:
        return False
    try:
        from yookassa import Payment as YooPayment
        payment = await _run_yookassa_sync_call(
            YooPayment.create,
            {
                "amount": {"value": f"{SUBSCRIPTION_PRICE_RUB:.2f}", "currency": "RUB"},
                "payment_method_id": payment_method_id,
                "capture": True,
                "save_payment_method": True,
                "description": "Продление подписки ASTROV - 399 ₽/месяц",
                "receipt": _build_receipt(
                    user=user,
                    description="Продление подписки ASTROV - 399 ₽/месяц",
                    amount_rub=float(SUBSCRIPTION_PRICE_RUB),
                ),
                "metadata": {
                    "user_id": str(user.telegram_id),
                    "payment_type": "subscription_renewal",
                },
            }
        )
    except Exception as exc:
        logger.warning("Recurring charge create failed user=%s: %s", user.telegram_id, exc, exc_info=True)
        exc_str = str(exc).lower()
        if "payment_method" in exc_str and ("not saved" in exc_str or "saved=true" in exc_str):
            user.subscription_payment_method_id = None
            await _deactivate_user_payment_methods(db, user_id=user.telegram_id, provider="yookassa")
            await db.flush()
            logger.info("Cleared invalid payment_method for user=%s", user.telegram_id)
        return False

    await _create_payment_record(
        db,
        user_id=user.telegram_id,
        yookassa_payment_id=payment.id,
        amount_cents=0,
        kind=kind,
        status="pending",
        metadata={"source": "billing_cycle"},
    )
    return True


async def _capture_payment(yookassa_payment_id: str) -> bool:
    if not _configure_yookassa():
        return False
    try:
        from yookassa import Payment as YooPayment
        await _run_yookassa_sync_call(
            YooPayment.capture,
            yookassa_payment_id,
            {"amount": {"value": f"{SUBSCRIPTION_PRICE_RUB:.2f}", "currency": "RUB"}},
        )
        return True
    except Exception as exc:
        logger.warning("Capture failed for payment=%s: %s", yookassa_payment_id, exc, exc_info=True)
        return False


async def _cancel_payment(yookassa_payment_id: str) -> bool:
    if not _configure_yookassa():
        return False
    try:
        from yookassa import Payment as YooPayment
        await _run_yookassa_sync_call(YooPayment.cancel, yookassa_payment_id)
        return True
    except Exception as exc:
        logger.warning("Cancel payment failed for payment=%s: %s", yookassa_payment_id, exc, exc_info=True)
        return False


async def cancel_subscription_for_user(db: AsyncSession, user_id: int) -> dict:
    user = (
        await db.execute(select(User).where(User.telegram_id == user_id).limit(1))
    ).scalar_one_or_none()
    if not user:
        return {"ok": False, "error": "Пользователь не найден."}

    user.subscription_canceled_at = _utcnow()
    user.subscription_next_charge_at = None
    user.subscription_payment_method_id = None
    await _deactivate_user_payment_methods(db, user_id=user_id, provider="yookassa")

    # Если у пользователя активен trial и есть авторизованный (но не списанный) платёж,
    # отменяем его, чтобы после trial не было списания.
    waiting_row = (
        await db.execute(
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.kind == "subscription",
                Payment.status == "waiting_for_capture",
            )
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if waiting_row and waiting_row.yookassa_payment_id:
        if await _cancel_payment(waiting_row.yookassa_payment_id):
            waiting_row.status = "canceled"
            waiting_row.updated_at = _utcnow()

    await db.flush()
    return {"ok": True}


async def run_billing_cycle(db: AsyncSession, *, limit_users: int = 200) -> dict:
    """
    Цикл автосписаний:
    - trial закончился -> пытаемся capture первого платежа (waiting_for_capture)
    - активная подписка -> списываем продление по сохраненному payment_method_id
    """
    now = _utcnow()
    users = (
        await db.execute(
            select(User)
            .where(
                User.subscription_canceled_at.is_(None),
                User.subscription_next_charge_at.is_not(None),
                User.subscription_next_charge_at <= now,
            )
            .limit(max(1, min(limit_users, 1000)))
        )
    ).scalars().all()

    processed = 0
    errors = 0
    for user in users:
        try:
            if user.status == "trial":
                waiting_row = (
                    await db.execute(
                        select(Payment)
                        .where(
                            Payment.user_id == user.telegram_id,
                            Payment.kind == "subscription",
                            Payment.status == "waiting_for_capture",
                        )
                        .order_by(Payment.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if waiting_row and waiting_row.yookassa_payment_id:
                    ok = await _capture_payment(waiting_row.yookassa_payment_id)
                    if ok:
                        processed += 1
                        continue
                # fallback: если capture не удалось, создаем обычное рекуррентное списание
                if await _create_recurring_charge(db, user=user, kind="subscription_renewal"):
                    processed += 1
                else:
                    errors += 1
            else:
                if await _create_recurring_charge(db, user=user, kind="subscription_renewal"):
                    processed += 1
                else:
                    errors += 1
        except Exception:
            errors += 1
            logger.exception("Billing cycle error for user=%s", user.telegram_id)

    await db.flush()
    return {"processed": processed, "errors": errors, "checked": len(users)}


def _status_to_webhook_event(status: str) -> str | None:
    s = (status or "").strip().lower()
    if s == "succeeded":
        return "payment.succeeded"
    if s == "waiting_for_capture":
        return "payment.waiting_for_capture"
    if s in {"canceled", "canceled_by_timeout"}:
        return "payment.canceled"
    return None


async def reconcile_pending_payments(db: AsyncSession, *, limit_rows: int = 200) -> dict:
    """Reconcile local pending payments with remote YooKassa status."""
    if not _configure_yookassa():
        return {"ok": False, "checked": 0, "updated": 0, "errors": 1, "unchanged": 0}
    try:
        from yookassa import Payment as YooPayment
    except Exception:
        logger.exception("YooKassa import failed during reconcile.")
        return {"ok": False, "checked": 0, "updated": 0, "errors": 1, "unchanged": 0}

    rows = (
        await db.execute(
            select(Payment)
            .where(
                Payment.status.in_(("pending", "waiting_for_capture")),
                Payment.yookassa_payment_id.is_not(None),
            )
            .order_by(Payment.created_at.asc())
            .limit(max(1, min(limit_rows, 1000)))
        )
    ).scalars().all()

    checked = 0
    updated = 0
    unchanged = 0
    errors = 0
    for row in rows:
        yk_id = (row.yookassa_payment_id or "").strip()
        if not yk_id:
            continue
        checked += 1
        try:
            remote = await _run_yookassa_sync_call(YooPayment.find_one, yk_id)
            remote_status = str(getattr(remote, "status", "") or "").strip().lower()
            if not remote_status:
                unchanged += 1
                continue
            if remote_status == (row.status or "").strip().lower():
                unchanged += 1
                continue
            event = _status_to_webhook_event(remote_status)
            if event:
                remote_metadata = getattr(remote, "metadata", None) or {}
                if not isinstance(remote_metadata, dict):
                    remote_metadata = {}
                payment_method_obj = getattr(remote, "payment_method", None)
                payment_method_id = str(getattr(payment_method_obj, "id", "") or "")
                amount_obj = getattr(remote, "amount", None)
                amount_value = str(getattr(amount_obj, "value", "0") or "0")
                income_obj = getattr(remote, "income_amount", None)
                income_value = str(getattr(income_obj, "value", "") or "")
                payload = {
                    "event": event,
                    "object": {
                        "id": yk_id,
                        "status": remote_status,
                        "amount": {"value": amount_value},
                        "metadata": {
                            "user_id": str(row.user_id),
                            "payment_type": str(remote_metadata.get("payment_type") or row.kind or ""),
                            **remote_metadata,
                        },
                        "payment_method": {"id": payment_method_id},
                    },
                }
                if income_value:
                    payload["object"]["income_amount"] = {"value": income_value}
                ok = await process_webhook(db, payload)
                if ok:
                    updated += 1
                else:
                    errors += 1
            else:
                row.status = remote_status
                row.updated_at = _utcnow()
                updated += 1
        except Exception:
            errors += 1
            logger.exception("Reconcile failed for payment_id=%s", yk_id)

    await db.flush()
    return {"ok": True, "checked": checked, "updated": updated, "errors": errors, "unchanged": unchanged}


async def process_webhook(db: AsyncSession, payload: dict) -> bool:
    """Обработка уведомлений YooKassa."""
    event_type = (payload.get("event") or "").strip()
    if event_type not in ("payment.succeeded", "payment.canceled", "payment.waiting_for_capture"):
        return False

    obj = payload.get("object") or {}
    yookassa_id = str(obj.get("id") or "").strip()
    status = str(obj.get("status") or "").strip()
    metadata = obj.get("metadata") or {}
    payment_method_id = _extract_payment_method_id(obj)

    if not yookassa_id:
        logger.warning("YooKassa webhook: missing payment id")
        return False

    payment_row = (
        await db.execute(
            select(Payment).where(Payment.yookassa_payment_id == yookassa_id).limit(1)
        )
    ).scalar_one_or_none()

    user_id_str = str(metadata.get("user_id") or "").strip()
    payment_type = str(metadata.get("payment_type") or "").strip()
    if payment_row:
        if not user_id_str:
            user_id_str = str(payment_row.user_id or "")
        if not payment_type:
            payment_type = str(payment_row.kind or "").strip()

    if not user_id_str:
        logger.warning("YooKassa webhook: missing user_id (payment=%s)", yookassa_id)
        return False
    try:
        user_id = int(user_id_str)
    except ValueError:
        logger.warning("YooKassa webhook: invalid user_id=%s", user_id_str)
        return False

    if not payment_row:
        # Для безопасности создаем запись, если webhook пришел раньше/в обход локальной записи.
        kind = payment_type or "unknown"
        payment_row = await _create_payment_record(
            db,
            user_id=user_id,
            yookassa_payment_id=yookassa_id,
            amount_cents=0,
            kind=kind,
            status="pending",
            metadata={"auto_created_from_webhook": True},
        )

    user = (
        await db.execute(select(User).where(User.telegram_id == user_id).limit(1))
    ).scalar_one_or_none()
    if not user:
        payment_row.status = "failed"
        payment_row.updated_at = _utcnow()
        await db.flush()
        return False

    now = _utcnow()
    amount = float((obj.get("amount") or {}).get("value") or 0)
    amount_cents = int(round(amount * 100))
    income_amount_rub = _extract_income_amount_rub(obj)
    computed_commission_rub: float | None = None
    if income_amount_rub is not None:
        computed_commission_rub = round(max(0.0, amount - income_amount_rub), 2)

    if event_type == "payment.waiting_for_capture" and payment_type == "subscription":
        if payment_row.status == "waiting_for_capture":
            return True
        payment_row.status = "waiting_for_capture"
        payment_row.amount_cents = amount_cents
        payment_row.updated_at = now
        _merge_payment_metadata(
            payment_row,
            webhook_event=event_type,
            yookassa_status=status,
            income_amount_rub=income_amount_rub,
            commission_rub=computed_commission_rub,
        )
        if payment_method_id:
            user.subscription_payment_method_id = payment_method_id
            await _upsert_user_payment_method(
                db,
                user_id=user_id,
                provider="yookassa",
                payment_method_id=payment_method_id,
                set_default=True,
                metadata={"source": "webhook_waiting_for_capture", "yookassa_payment_id": yookassa_id},
            )
        # Пробный период запускаем только один раз.
        if not user.is_trial_used:
            trial_ends_at = now + timedelta(days=TRIAL_DAYS)
            user.is_trial_used = True
            user.status = "trial"
            user.trial_ends_at = trial_ends_at
            user.subscription_next_charge_at = trial_ends_at
            user.subscription_canceled_at = None
        await db.flush()
        return True

    if status != "succeeded":
        payment_row.status = "failed" if status in ("canceled", "canceled_by_timeout") else status
        payment_row.updated_at = now
        _merge_payment_metadata(
            payment_row,
            webhook_event=event_type,
            yookassa_status=status,
            income_amount_rub=income_amount_rub,
            commission_rub=computed_commission_rub,
        )
        await db.flush()
        return True

    # Idempotency guard: repeated succeeded webhook must not duplicate balance/revenue/expense.
    if payment_row.status == "succeeded":
        _merge_payment_metadata(
            payment_row,
            webhook_event=event_type,
            yookassa_status=status,
            income_amount_rub=income_amount_rub,
            commission_rub=computed_commission_rub,
        )
        await db.flush()
        return True

    payment_row.status = "succeeded"
    payment_row.amount_cents = amount_cents
    payment_row.updated_at = now
    _merge_payment_metadata(
        payment_row,
        webhook_event=event_type,
        yookassa_status=status,
        income_amount_rub=income_amount_rub,
        commission_rub=computed_commission_rub,
    )

    if payment_method_id and payment_type not in VIP_TARIFFS:
        user.subscription_payment_method_id = payment_method_id
        await _upsert_user_payment_method(
            db,
            user_id=user_id,
            provider="yookassa",
            payment_method_id=payment_method_id,
            set_default=payment_type in {"subscription", "subscription_renewal"},
            metadata={"source": "webhook_succeeded", "yookassa_payment_id": yookassa_id},
        )

    if payment_type == "topup":
        user.balance_cents = (getattr(user, "balance_cents", 0) or 0) + amount_cents
        await add_balance_ledger_on_topup(db, user_id, amount_cents, payment_id=payment_row.id)
    elif payment_type in {"subscription", "subscription_renewal"}:
        end = _to_aware(user.subscription_end_date)
        start = end if end and end > now else now
        user.subscription_end_date = start + timedelta(days=31 * SUBSCRIPTION_MONTHS)
        user.subscription_next_charge_at = user.subscription_end_date
        user.subscription_canceled_at = None
        user.status = "full_access"
    elif payment_type in VIP_TARIFFS:
        _, days = VIP_TARIFFS[payment_type]
        end = _to_aware(user.subscription_end_date)
        start = end if end and end > now else now
        user.subscription_end_date = start + timedelta(days=days)
        user.subscription_next_charge_at = None
        user.subscription_canceled_at = None
        user.status = "full_access"

    # Записать доход в Revenue для отображения в админке
    revenue_types = ("topup", "subscription", "subscription_renewal") + tuple(VIP_TARIFFS.keys())
    if amount_cents > 0 and payment_type in revenue_types:
        amount_rub = amount_cents / 100.0
        period_date = now.date()
        db.add(Revenue(period_date=period_date, amount=amount_rub, payment_id=payment_row.id))
        # Автоматический учёт комиссии ЮKassa:
        # 1) точное значение из income_amount (если пришло),
        # 2) fallback на конфигурируемый %.
        commission_rub = computed_commission_rub
        if commission_rub is None:
            rate = float(get_settings().YOOKASSA_COMMISSION_PERCENT or 0)
            commission_rub = round(amount_rub * (rate / 100.0), 2) if rate > 0 else 0.0
        if (commission_rub or 0) > 0:
            db.add(Expense(period_date=period_date, category="commission", amount=float(commission_rub)))

    await db.flush()

    try:
        await process_referral_bonus_for_successful_payment(
            db,
            payer_telegram_id=user_id,
            payment_row=payment_row,
            payment_type=str(payment_type or ""),
            amount_cents=int(amount_cents or 0),
        )
        await db.flush()
    except Exception:
        logger.exception("Referral bonus failed for payment id=%s user=%s", payment_row.id, user_id)

    logger.info(
        "YooKassa webhook processed user=%s payment=%s type=%s status=%s amount=%s",
        user_id,
        yookassa_id,
        payment_type,
        event_type,
        amount_cents,
    )
    return True


async def verify_webhook_payment_payload(payload: dict) -> bool:
    """
    Verify webhook payload against YooKassa API state.
    Prevents forged local webhook calls with arbitrary user_id/amount.
    """
    try:
        event_type = str((payload or {}).get("event") or "").strip()
        if event_type not in ("payment.succeeded", "payment.canceled", "payment.waiting_for_capture"):
            return False
        obj = (payload or {}).get("object") or {}
        payment_id = str(obj.get("id") or "").strip()
        if not payment_id:
            return False
        if not _configure_yookassa():
            logger.warning("Webhook verify skipped: YooKassa not configured")
            return False
        from yookassa import Payment as YooPayment

        remote = await _run_yookassa_sync_call(YooPayment.find_one, payment_id)
        remote_status = str(getattr(remote, "status", "") or "").strip().lower()
        local_status = str(obj.get("status") or "").strip().lower()
        if remote_status and local_status and remote_status != local_status:
            logger.warning("Webhook verify failed: status mismatch payment=%s local=%s remote=%s", payment_id, local_status, remote_status)
            return False

        remote_amount_obj = getattr(remote, "amount", None)
        remote_amount = str(getattr(remote_amount_obj, "value", "") or "").strip()
        local_amount = str(((obj.get("amount") or {}).get("value") or "")).strip()
        if remote_amount and local_amount and remote_amount != local_amount:
            logger.warning("Webhook verify failed: amount mismatch payment=%s local=%s remote=%s", payment_id, local_amount, remote_amount)
            return False

        remote_meta = getattr(remote, "metadata", None) or {}
        if isinstance(remote_meta, dict):
            local_meta = obj.get("metadata") or {}
            remote_user = str(remote_meta.get("user_id") or "").strip()
            local_user = str(local_meta.get("user_id") or "").strip()
            if remote_user and local_user and remote_user != local_user:
                logger.warning("Webhook verify failed: user mismatch payment=%s local=%s remote=%s", payment_id, local_user, remote_user)
                return False
            remote_type = str(remote_meta.get("payment_type") or "").strip()
            local_type = str(local_meta.get("payment_type") or "").strip()
            if remote_type and local_type and remote_type != local_type:
                logger.warning("Webhook verify failed: payment_type mismatch payment=%s local=%s remote=%s", payment_id, local_type, remote_type)
                return False
        return True
    except Exception as exc:
        logger.warning("Webhook verify failed: %s", exc)
        return False
