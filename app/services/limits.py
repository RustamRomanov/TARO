"""
Limit and access policy: check_limits, reset daily counters, trial, balance.

Политика тарифа:
- Платные функции доступны при активном пробном периоде, при активной подписке
  (subscription_end_date в будущем) или при статусе full_access без даты окончания (вечная выдача).
- Если задана subscription_end_date и она в прошлом, доступ по тарифу VIP считается завершённым:
  остаются оплата с баланса и разовый бесплатный первый расклад каждого типа Таро (см. has_welcome_free_access).
- Версии тарифа (balance_ledger.tariff_version): пополнения через ЮKassa получают текущую версию;
  списание FIFO. Для расклада Таро цена берётся по версии пула самой старой ненулевой записи,
  если это не бонус от Администрации: бонусные начисления (payments.kind = bonus_admin) тарифицируются
  по актуальной версии. Толкование снов бесплатно.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BalanceLedger,
    History,
    HistoryType,
    Payment,
    Profile,
    TarotReading,
    User,
)

# --- Constants ---

USER_STATUS_FREE = "free"
USER_STATUS_TRIAL = "trial"
USER_STATUS_FULL_ACCESS = "full_access"

TRIAL_DAYS = 3

# Подписка: безлимит, но защита от злоупотребления - 30+ подряд за час
CONSECUTIVE_ABUSE_WINDOW_MINUTES = 60
CONSECUTIVE_ABUSE_THRESHOLD = 30
MSG_OVERLOAD = "Система перегружена. Повторите попытку позже."

# Версия тарифов: при смене - новая стоимость для новых пополнений (см. юридический текст)
CURRENT_TARIFF_VERSION = 2

# Тарифы по версиям (копейки): feature -> cents
TARIFF_V1 = {
    "dream": 0,             # исторически 3 ₽; далее бесплатно
    "tarot": 500,           # 5 ₽ до исчерпания старых пополнений (не bonus_admin)
    "vision": 1000,         # 10★ (лицо/ладонь/совместимость)
    "forecast_day": 200,    # 2★
    "forecast_month": 200,
    "forecast_year": 200,
    "shadow": 500,          # 5★
    "natal": 5000,          # 50★
    "compatibility": 2000,  # 20★ (совместимость по датам)
    "keys": 5000,           # 50★
    "profile_add": 10000,   # 100★
}
TARIFF_V2 = {
    **TARIFF_V1,
    "dream": 0,
    "tarot": 1000,          # 10 ₽ для новых пополнений и бонусных пулов
}
TARIFF_VERSIONS: dict[int, dict[str, int]] = {1: TARIFF_V1, 2: TARIFF_V2}

# Обратная совместимость (экспорт для старых импортов)
PRICE_TAROT_CENTS = TARIFF_V2["tarot"]
PRICE_VISION_CENTS = TARIFF_V2["vision"]
PRICE_DREAM_CENTS = 0

# Начисления с этим kind в payments считаются бонусом: для Таро цена по CURRENT_TARIFF_VERSION
BONUS_LEDGER_PAYMENT_KINDS = frozenset({"bonus_admin", "referral_bonus"})

MSG_LIMIT = "Лимит исчерпан. Оформите Тариф VIP или пополните баланс для продолжения."
MSG_BALANCE = "Недостаточно средств. Пополните баланс или оформите Тариф VIP."

# TARO: бесплатные расклады с дневным лимитом (оплата скрыта на этапе запуска)
FREE_TAROT_DAILY_LIMIT = 5
MSG_TAROT_DAILY_LIMIT = "Вы исчерпали лимит раскладов на сегодня. Приходите завтра."

# Коды раскладов в TarotReading.spread_code (совпадают с SPREADS в app.api.tarot_routes)
TAROT_SPREAD_CODES: tuple[str, ...] = ("single", "three_cards", "financial", "six_cards", "ten_cards")


async def _recent_usage_count(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
) -> int:
    """Количество использований feature_type за последний CONSECUTIVE_ABUSE_WINDOW_MINUTES минут."""
    since = datetime.now(timezone.utc) - timedelta(minutes=CONSECUTIVE_ABUSE_WINDOW_MINUTES)
    if feature_type == "tarot":
        r = await db.execute(
            select(func.count()).select_from(TarotReading).where(
                TarotReading.user_id == telegram_id,
                TarotReading.created_at >= since,
            )
        )
        return r.scalar() or 0
    if feature_type == "vision":
        r = await db.execute(
            select(func.count()).select_from(History).where(
                History.user_id == telegram_id,
                History.type == HistoryType.VISION,
                History.created_at >= since,
            )
        )
        return r.scalar() or 0
    if feature_type == "dream":
        r = await db.execute(
            select(func.count()).select_from(History).where(
                History.user_id == telegram_id,
                History.type == HistoryType.DREAM,
                History.created_at >= since,
            )
        )
        return r.scalar() or 0
    return 0


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _utc_day_bounds() -> tuple[datetime, datetime]:
    """Начало и конец текущих суток UTC для фильтрации created_at."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


async def count_tarot_readings_utc_today(
    db: AsyncSession,
    telegram_id: int,
    spread_code: str,
) -> int:
    start, end = _utc_day_bounds()
    r = await db.execute(
        select(func.count())
        .select_from(TarotReading)
        .where(
            TarotReading.user_id == telegram_id,
            TarotReading.spread_code == spread_code,
            TarotReading.created_at >= start,
            TarotReading.created_at < end,
        )
    )
    return int(r.scalar() or 0)


async def _count_history_tarot_today(db: AsyncSession, telegram_id: int) -> int:
    """Записи History TAROT за сегодня (UTC): запасной путь /api/tarot/draw без tarot_readings."""
    start, end = _utc_day_bounds()
    r = await db.execute(
        select(func.count())
        .select_from(History)
        .where(
            History.user_id == telegram_id,
            History.type == HistoryType.TAROT,
            History.created_at >= start,
            History.created_at < end,
        )
    )
    return int(r.scalar() or 0)


async def tarot_single_like_usage_today(db: AsyncSession, telegram_id: int) -> int:
    """Сколько раз сегодня уже учтён расклад «1 карта»: tarot_readings.single + history tarot."""
    tr = await count_tarot_readings_utc_today(db, telegram_id, "single")
    hr = await _count_history_tarot_today(db, telegram_id)
    return tr + hr


async def count_all_tarot_readings_utc_today(db: AsyncSession, telegram_id: int) -> int:
    """Все расклады Таро за текущие сутки UTC (tarot_readings + legacy history)."""
    start, end = _utc_day_bounds()
    r = await db.execute(
        select(func.count())
        .select_from(TarotReading)
        .where(
            TarotReading.user_id == telegram_id,
            TarotReading.created_at >= start,
            TarotReading.created_at < end,
        )
    )
    tr = int(r.scalar() or 0)
    hr = await _count_history_tarot_today(db, telegram_id)
    return tr + hr


async def _ensure_user(
    db: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> User:
    """Get or create user. On create: status=free, counters=0, last_reset_date=today.
    When user exists and username/full_name are provided (from init_data), updates them.
    """
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is not None:
        # Обновляем только при реальном изменении, чтобы не писать в БД на каждом запросе.
        changed = False
        if username is not None:
            normalized_username = username.strip() or None
            if user.username != normalized_username:
                user.username = normalized_username
                changed = True
        if full_name is not None:
            normalized_full_name = full_name.strip() or None
            if user.full_name != normalized_full_name:
                user.full_name = normalized_full_name
                changed = True
        if changed:
            await db.flush()
        return user
    user = User(
        telegram_id=telegram_id,
        username=(username or "").strip() or None,
        full_name=(full_name or "").strip() or None,
        status=USER_STATUS_FREE,
        daily_tarot=0,
        daily_vision=0,
        daily_dreams=0,
        last_reset_date=_utc_today(),
    )
    db.add(user)
    await db.flush()
    return user


async def _reset_daily_if_needed(db: AsyncSession, user: User) -> User:
    """If last_reset_date < today (UTC), set counters to 0 and last_reset_date = today."""
    today = _utc_today()
    if user.last_reset_date is None or user.last_reset_date < today:
        await db.execute(
            update(User)
            .where(User.telegram_id == user.telegram_id)
            .values(
                daily_tarot=0,
                daily_vision=0,
                daily_dreams=0,
                last_reset_date=today,
            )
            .execution_options(synchronize_session="fetch")
        )
        await db.flush()
        user.daily_tarot = 0
        user.daily_vision = 0
        user.daily_dreams = 0
        user.last_reset_date = today
    return user


def has_paid_access(user: User) -> bool:
    """Публичная проверка: подписка или пробный период активны."""
    return _has_full_access(user)


def has_vip_tariff(user: User) -> bool:
    """
    Тариф VIP (без списания с баланса за ключи мандалы):
    статус full_access без срока, либо subscription_end_date ещё в будущем.
    Пробный trial сюда не входит, оплата с баланса обязательна.
    """
    now = datetime.now(timezone.utc)
    sub_end = getattr(user, "subscription_end_date", None)
    if sub_end is not None:
        end = sub_end.replace(tzinfo=timezone.utc) if sub_end.tzinfo is None else sub_end
        if end > now:
            return True
    status_val = (user.status or "").strip().lower()
    if status_val == USER_STATUS_FULL_ACCESS and sub_end is None:
        return True
    return False


def _has_full_access(user: User) -> bool:
    """Подписка по дате, пробный период или бессрочный full_access в админке."""
    now = datetime.now(timezone.utc)
    sub_end = getattr(user, "subscription_end_date", None)
    if sub_end is not None:
        end = sub_end.replace(tzinfo=timezone.utc) if sub_end.tzinfo is None else sub_end
        if end > now:
            return True
    status_val = (user.status or "").strip().lower()
    if status_val == USER_STATUS_FULL_ACCESS and sub_end is None:
        return True
    if user.status == USER_STATUS_TRIAL and user.trial_ends_at:
        te = user.trial_ends_at.replace(tzinfo=timezone.utc) if user.trial_ends_at.tzinfo is None else user.trial_ends_at
        return te > now
    return False


async def sync_expired_subscription_status(db: AsyncSession, user: User) -> None:
    """
    После истечения subscription_end_date снимает full_access, чтобы доступ совпадал с политикой тарифа.
    Данные оплаты и дата окончания в БД сохраняются для истории.
    """
    sub = getattr(user, "subscription_end_date", None)
    if sub is None:
        return
    now = datetime.now(timezone.utc)
    end = sub.replace(tzinfo=timezone.utc) if sub.tzinfo is None else sub
    if end > now:
        return
    status_val = (user.status or "").strip().lower()
    if status_val == USER_STATUS_FULL_ACCESS:
        user.status = USER_STATUS_FREE
        await db.flush()


def _price_cents(feature_type: str, tariff_version: int | None = None) -> int:
    ver = tariff_version if tariff_version is not None else CURRENT_TARIFF_VERSION
    prices = TARIFF_VERSIONS.get(ver, TARIFF_V1)
    return prices.get(feature_type, 0)


async def _effective_price_for_deduct(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
) -> int:
    """Цена по тарифу самой старой непотраченной части баланса (FIFO)."""
    ft = (feature_type or "").strip().lower()
    if ft == "dream":
        return 0

    r = await db.execute(
        select(BalanceLedger)
        .where(BalanceLedger.user_id == telegram_id, BalanceLedger.amount_cents > 0)
        .order_by(BalanceLedger.created_at.asc())
        .limit(1)
    )
    entry = r.scalar_one_or_none()
    if not entry:
        return _price_cents(ft, CURRENT_TARIFF_VERSION)

    ver = entry.tariff_version
    if ft == "tarot" and entry.payment_id is not None:
        pay = await db.get(Payment, entry.payment_id)
        if pay is not None and (pay.kind or "") in BONUS_LEDGER_PAYMENT_KINDS:
            ver = CURRENT_TARIFF_VERSION

    return _price_cents(ft, ver)


async def check_limits(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
    profiles_count: int | None = None,
    usage_key: str | None = None,
) -> User:
    """
    Check access for feature_type in ('profiles', 'tarot', 'vision', 'dream').
    Ensures user exists, resets daily counters if needed, then applies policy.
    Raises HTTPException 403 if limit exceeded. Returns User model.
    """
    user = await _ensure_user(db, telegram_id)
    user = await _reset_daily_if_needed(db, user)
    paid = _has_full_access(user)

    if feature_type == "profiles":
        # Profile count is not limited anymore.
        return user

    if feature_type == "tarot":
        if paid:
            recent = await _recent_usage_count(db, telegram_id, "tarot")
            if recent >= CONSECUTIVE_ABUSE_THRESHOLD:
                raise HTTPException(status_code=503, detail=MSG_OVERLOAD)
            return user
        used_today = await count_all_tarot_readings_utc_today(db, telegram_id)
        if used_today >= FREE_TAROT_DAILY_LIMIT:
            raise HTTPException(status_code=403, detail=MSG_TAROT_DAILY_LIMIT)
        return user

    if feature_type == "vision":
        if paid:
            recent = await _recent_usage_count(db, telegram_id, "vision")
            if recent >= CONSECUTIVE_ABUSE_THRESHOLD:
                raise HTTPException(status_code=503, detail=MSG_OVERLOAD)
        else:
            if await has_welcome_free_access(db, telegram_id, "vision", usage_key=usage_key):
                return user
            price = await _effective_price_for_deduct(db, telegram_id, "vision")
            balance = getattr(user, "balance_cents", 0) or 0
            if balance < price:
                raise HTTPException(status_code=403, detail=MSG_BALANCE)
        return user

    if feature_type == "dream":
        if paid:
            recent = await _recent_usage_count(db, telegram_id, "dream")
            if recent >= CONSECUTIVE_ABUSE_THRESHOLD:
                raise HTTPException(status_code=503, detail=MSG_OVERLOAD)
        return user

    for ft in ("forecast_day", "forecast_month", "forecast_year", "shadow", "natal", "compatibility", "keys", "profile_add"):
        if feature_type == ft:
            # Ключи авторской мандалы: бесплатно только у Тарифа VIP, не у trial.
            if ft == "keys":
                if has_vip_tariff(user):
                    return user
                price = await _effective_price_for_deduct(db, telegram_id, ft)
                balance = getattr(user, "balance_cents", 0) or 0
                if balance < price:
                    raise HTTPException(status_code=403, detail=MSG_BALANCE)
                return user
            if paid:
                return user
            price = await _effective_price_for_deduct(db, telegram_id, ft)
            balance = getattr(user, "balance_cents", 0) or 0
            if balance < price:
                raise HTTPException(status_code=403, detail=MSG_BALANCE)
            return user

    return user


async def increment_daily(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
) -> None:
    """Increment the corresponding daily counter for the user."""
    col = {
        "tarot": User.daily_tarot,
        "vision": User.daily_vision,
        "dream": User.daily_dreams,
    }.get(feature_type)
    if col is None:
        return
    await db.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values({col: col + 1})
        .execution_options(synchronize_session="fetch")
    )
    await db.flush()


def get_limits_response(user: User) -> dict:
    """Return limits and pricing for API: tarot/dream/vision limit, used, balance, subscription, trial, prices."""
    now = datetime.now(timezone.utc)
    paid = _has_full_access(user)
    sub_days_remaining: int | None = None
    sub = getattr(user, "subscription_end_date", None)
    if sub is not None:
        end = sub.replace(tzinfo=timezone.utc) if sub.tzinfo is None else sub
        if end > now:
            sub_days_remaining = max(0, (end.date() - now.date()).days)
    limit_val = None  # безлимит для подписчиков
    p = TARIFF_VERSIONS.get(CURRENT_TARIFF_VERSION, TARIFF_V2)
    return {
        "tarot": {"limit": limit_val, "used": user.daily_tarot, "price_cents": p["tarot"]},
        "vision": {"limit": limit_val, "used": user.daily_vision, "price_cents": p["vision"]},
        "dreams": {"limit": limit_val, "used": user.daily_dreams, "price_cents": p["dream"]},
        "forecast_day": {"price_cents": p["forecast_day"]},
        "forecast_month": {"price_cents": p["forecast_month"]},
        "forecast_year": {"price_cents": p["forecast_year"]},
        "shadow": {"price_cents": p["shadow"]},
        "natal": {"price_cents": p["natal"]},
        "compatibility": {"price_cents": p["compatibility"]},
        "keys": {"price_cents": p["keys"]},
        "profile_add": {"price_cents": p["profile_add"]},
        "balance_cents": getattr(user, "balance_cents", 0) or 0,
        "subscription_end_date": user.subscription_end_date.isoformat() if user.subscription_end_date else None,
        "subscription_next_charge_at": (
            user.subscription_next_charge_at.isoformat() if getattr(user, "subscription_next_charge_at", None) else None
        ),
        "subscription_canceled_at": (
            user.subscription_canceled_at.isoformat() if getattr(user, "subscription_canceled_at", None) else None
        ),
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "is_trial_used": getattr(user, "is_trial_used", False),
        "is_paid": paid,
        "subscription_days_remaining": sub_days_remaining,
    }


async def tarot_welcome_eligibility_map(db: AsyncSession, telegram_id: int) -> dict[str, bool]:
    """Для UI: по каждому коду расклада True, если пользователь ещё не сохранял такой расклад."""
    r = await db.execute(select(TarotReading.spread_code).where(TarotReading.user_id == telegram_id))
    had = set(r.scalars().all())
    return {code: code not in had for code in TAROT_SPREAD_CODES}


async def build_limits_for_auth(db: AsyncSession, user: User) -> dict:
    """Лимиты для ответа auth: добавляет tarot.welcome_by_spread для Mini App."""
    base = get_limits_response(user)
    welcome = await tarot_welcome_eligibility_map(db, user.telegram_id)
    tid = user.telegram_id
    tarot = dict(base["tarot"])
    tarot["welcome_by_spread"] = welcome
    tarot["price_cents"] = await _effective_price_for_deduct(db, tid, "tarot")
    out = dict(base)
    out["tarot"] = tarot
    dreams = dict(base["dreams"])
    dreams["price_cents"] = 0
    out["dreams"] = dreams
    return out


async def deduct_balance(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
    request_content: str | None = None,
) -> None:
    """
    Списать с баланса стоимость использования (FIFO по тарифу на момент пополнения).
    Вызывать после успешного выполнения действия. 403 если недостаточно средств.
    """
    price = await _effective_price_for_deduct(db, telegram_id, feature_type)
    if price <= 0:
        return
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    balance = getattr(user, "balance_cents", 0) or 0
    if balance < price:
        raise HTTPException(status_code=403, detail=MSG_BALANCE)

    # FIFO: consume from oldest ledger entries
    remaining = price
    r = await db.execute(
        select(BalanceLedger)
        .where(BalanceLedger.user_id == telegram_id, BalanceLedger.amount_cents > 0)
        .order_by(BalanceLedger.created_at.asc())
    )
    entries = list(r.scalars().all())
    for entry in entries:
        if remaining <= 0:
            break
        take = min(entry.amount_cents, remaining)
        entry.amount_cents -= take
        remaining -= take

    await db.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(balance_cents=User.balance_cents - price)
        .execution_options(synchronize_session="fetch")
    )
    kind = f"deduct_{feature_type}"
    payment = Payment(
        user_id=telegram_id,
        amount_cents=-price,
        kind=kind,
        status="succeeded",
    )
    db.add(payment)
    _hist_type = {
        "natal": HistoryType.NATAL,
        "compatibility": HistoryType.NUMEROLOGY,
        "keys": HistoryType.KEYS,
        "shadow": HistoryType.SHADOW,
        "forecast_day": HistoryType.FORECAST,
        "forecast_month": HistoryType.FORECAST,
        "forecast_year": HistoryType.FORECAST,
    }.get(feature_type)
    if _hist_type is not None:
        hist = History(
            user_id=telegram_id,
            type=_hist_type,
            request_content=request_content or feature_type,
            response_content=None,
        )
        db.add(hist)
    await db.flush()


async def add_balance_ledger_on_topup(
    db: AsyncSession,
    telegram_id: int,
    amount_cents: int,
    payment_id: int | None = None,
) -> None:
    """Добавить запись в ledger при успешном пополнении (тариф на момент пополнения)."""
    entry = BalanceLedger(
        user_id=telegram_id,
        amount_cents=amount_cents,
        tariff_version=CURRENT_TARIFF_VERSION,
        payment_id=payment_id,
    )
    db.add(entry)
    await db.flush()


async def can_access_feature(db: AsyncSession, telegram_id: int, feature: str) -> bool:
    """
    Feature gate helper for monetized modules.

    Free features:
    - destiny_matrix_basic
    Paid/trial features:
    - destiny_ai
    - numerology_compatibility_ai
    - numerology_forecast_ai
    """
    user = await _ensure_user(db, telegram_id)
    if feature == "destiny_matrix_basic":
        return True
    return _has_full_access(user)


async def has_welcome_free_access(
    db: AsyncSession,
    telegram_id: int,
    feature_type: str,
    *,
    usage_key: str | None = None,
) -> bool:
    """
    One-time free tries for first-time users by feature scope:
    - tarot: one free per spread (usage_key=spread_code)
    - vision: one free per subtype (usage_key=face|palm|compatibility)
    - dream: one free first interpretation
    """
    ft = (feature_type or "").strip().lower()
    key = (usage_key or "").strip().lower()

    if ft == "tarot":
        spread = key or "single"
        row = await db.execute(
            select(TarotReading.id)
            .where(TarotReading.user_id == telegram_id, TarotReading.spread_code == spread)
            .limit(1)
        )
        if row.scalar_one_or_none() is not None:
            return False
        return True

    return False
