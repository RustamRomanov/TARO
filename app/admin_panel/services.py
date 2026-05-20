"""Сервисы админки: агрегации для дашборда, пользователей, статистики, финансов."""
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import String, and_, case, cast, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    AdminSetting,
    Expense,
    Feedback,
    FeedbackAttachment,
    FeedbackReply,
    History,
    HistoryType,
    Payment,
    Revenue,
    User,
)
from app.db.models.admin_setting import ADMIN_SETTING_USD_RUB
from app.db.models.token_usage import TokenUsage
from app.db.models.expense import EXPENSE_CATEGORY_LABELS
from app.services.limits import add_balance_ledger_on_topup
from app.services.token_calculator import calculate_cost

# Бонусы в отчётах: ручные от админа и реферальные начисления
_BONUS_PAYMENT_KINDS_FOR_STATS = ("bonus_admin", "referral_bonus")


def _payment_kind_label_ru(kind: str) -> str:
    k = (kind or "").strip()
    if k == "referral_bonus":
        return "Реферальный бонус"
    if k == "bonus_admin":
        return "Бонус (администрация)"
    if k.startswith("deduct_"):
        return f"Списание: {k.replace('deduct_', '')}"
    return k or "-"
from app.services.token_calculator import get_exchange_rate as _auto_get_exchange_rate
from app.services.token_calculator import update_exchange_rate as _auto_update_exchange_rate

logger = logging.getLogger(__name__)


async def get_dashboard_kpis(session: AsyncSession) -> dict[str, Any]:
    """KPI для дашборда: всего пользователей, периодические, с подпиской, отписавшиеся."""
    # 1. Всего попробовавших
    r = await session.execute(select(func.count()).select_from(User))
    total_users = r.scalar() or 0

    # 2. Периодические за 7 дней по последнему факту визита/активности.
    # Приоритет: max(history.created_at, users.last_seen_at), fallback users.created_at.
    week_ago = datetime.utcnow() - timedelta(days=7)
    history_last_subq = (
        select(
            History.user_id.label("user_id"),
            func.max(History.created_at).label("last_history_at"),
        )
        .group_by(History.user_id)
        .subquery()
    )
    history_last_expr = history_last_subq.c.last_history_at
    seen_last_expr = User.last_seen_at
    latest_touch_expr = case(
        (history_last_expr.is_(None), seen_last_expr),
        (seen_last_expr.is_(None), history_last_expr),
        (history_last_expr >= seen_last_expr, history_last_expr),
        else_=seen_last_expr,
    )
    last_activity_expr = func.coalesce(latest_touch_expr, User.created_at)
    r = await session.execute(
        select(func.count())
        .select_from(User)
        .outerjoin(history_last_subq, history_last_subq.c.user_id == User.telegram_id)
        .where(last_activity_expr >= week_ago)
    )
    periodic_users = r.scalar() or 0

    # 3. С подпиской (full_access)
    r = await session.execute(select(func.count()).select_from(User).where(User.status == "full_access"))
    subscribed = r.scalar() or 0

    # 4. Отписавшиеся - пока нет истории смены статуса, считаем 0 или free с истёкшей подпиской
    r = await session.execute(
        select(func.count()).select_from(User).where(User.status == "free", User.subscription_end_date != None)
    )
    unsubscribed = r.scalar() or 0

    # 5. Пользователи с положительным балансом.
    r = await session.execute(select(func.count()).select_from(User).where(User.balance_cents > 0))
    users_with_balance = int(r.scalar() or 0)

    r = await session.execute(select(func.count()).select_from(User).where(User.bot_stopped_at.isnot(None)))
    bot_stopped_users = int(r.scalar() or 0)

    return {
        "total_users": total_users,
        "periodic_users": periodic_users,
        "subscribed": subscribed,
        "unsubscribed": unsubscribed,
        "users_with_balance": users_with_balance,
        "bot_stopped_users": bot_stopped_users,
    }


def _age_bucket(age: int) -> str:
    if age < 18:
        return "до 18"
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 45:
        return "36-45"
    if age <= 55:
        return "45-55"
    return "55+"


async def get_gender_age_distribution(session: AsyncSession) -> dict[str, Any]:
    """TARO: нет профилей с датой рождения — пустая статистика."""
    _ = session
    age_order = ["до 18", "18-25", "26-35", "36-45", "45-55", "55+"]
    age_buckets = {b: 0 for b in age_order}
    by_gender: dict[str, int] = {}
    pyramid: dict[str, dict[str, int]] = {b: {"male": 0, "female": 0} for b in age_order}

    pyramid_list = [
        {"age": b, "male": pyramid[b]["male"], "female": pyramid[b]["female"]}
        for b in age_order
    ]
    return {"by_gender": by_gender, "by_age": age_buckets, "pyramid": pyramid_list}


async def get_revenue_series(session: AsyncSession, days: int = 30) -> list[dict]:
    """Сумма поступлений по дням за последние days дней."""
    start = date.today() - timedelta(days=days)
    r = await session.execute(
        select(Revenue.period_date, func.sum(Revenue.amount)).where(Revenue.period_date >= start).group_by(Revenue.period_date)
    )
    by_date = {row[0]: float(row[1]) for row in r.all()}
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        result.append({"date": d.isoformat(), "amount": by_date.get(d, 0)})
    return result


async def get_bonus_series(session: AsyncSession, days: int = 30) -> list[dict]:
    """Сумма бонусных начислений по дням за последние days дней."""
    start = date.today() - timedelta(days=days)
    r = await session.execute(
        select(func.date(Payment.created_at), func.sum(Payment.amount_cents))
        .select_from(Payment)
        .where(
            Payment.status == "succeeded",
            Payment.amount_cents > 0,
            Payment.kind.in_(_BONUS_PAYMENT_KINDS_FOR_STATS),
            func.date(Payment.created_at) >= start,
        )
        .group_by(func.date(Payment.created_at))
    )
    by_date: dict[date, float] = {}
    for row in r.all():
        key = row[0]
        d_key = key if isinstance(key, date) else date.fromisoformat(str(key)[:10])
        by_date[d_key] = float((row[1] or 0) / 100.0)
    result = []
    for i in range(days):
        d = start + timedelta(days=i)
        result.append({"date": d.isoformat(), "amount": by_date.get(d, 0.0)})
    return result


def _first_day_n_months_ago(today: date, n: int) -> date:
    """Первый день месяца n месяцев назад (n=0 - текущий месяц)."""
    ref = today.replace(day=1)
    for _ in range(n):
        ref = (ref - timedelta(days=1)).replace(day=1)
    return ref


async def get_revenue_series_monthly(session: AsyncSession, months: int = 12) -> list[dict]:
    """Сумма поступлений по месяцам за последние months месяцев (от старых к новым)."""
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        month_start = _first_day_n_months_ago(today, i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if month_end > today:
            month_end = today
        r = await session.execute(
            select(func.coalesce(func.sum(Revenue.amount), 0)).select_from(Revenue).where(
                Revenue.period_date >= month_start,
                Revenue.period_date <= month_end,
            )
        )
        amount = float(r.scalar() or 0)
        result.append({"date": month_start.isoformat(), "label": month_start.strftime("%b %Y"), "amount": amount})
    return result


async def get_bonus_series_monthly(session: AsyncSession, months: int = 12) -> list[dict]:
    """Сумма бонусных начислений по месяцам за последние months месяцев."""
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        month_start = _first_day_n_months_ago(today, i)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if month_end > today:
            month_end = today
        r = await session.execute(
            select(func.coalesce(func.sum(Payment.amount_cents), 0))
            .select_from(Payment)
            .where(
                Payment.status == "succeeded",
                Payment.amount_cents > 0,
                Payment.kind.in_(_BONUS_PAYMENT_KINDS_FOR_STATS),
                func.date(Payment.created_at) >= month_start,
                func.date(Payment.created_at) <= month_end,
            )
        )
        amount = float((r.scalar() or 0) / 100.0)
        result.append({"date": month_start.isoformat(), "label": month_start.strftime("%b %Y"), "amount": amount})
    return result


async def get_revenue_totals(session: AsyncSession) -> dict[str, float]:
    """Сумма за день, неделю, месяц и всего."""
    today = date.today()
    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)
    r = await session.execute(select(func.sum(Revenue.amount)).select_from(Revenue).where(Revenue.period_date == today))
    day = float(r.scalar() or 0)
    r = await session.execute(
        select(func.sum(Revenue.amount)).select_from(Revenue).where(Revenue.period_date >= week_start)
    )
    week = float(r.scalar() or 0)
    r = await session.execute(
        select(func.sum(Revenue.amount)).select_from(Revenue).where(Revenue.period_date >= month_start)
    )
    month = float(r.scalar() or 0)
    r = await session.execute(select(func.sum(Revenue.amount)).select_from(Revenue))
    total = float(r.scalar() or 0)
    return {"day": day, "week": week, "month": month, "total": total}


async def get_bonus_totals(session: AsyncSession) -> dict[str, float]:
    """Сумма бонусных начислений (админ и реферальная программа) за день, неделю, месяц и всего."""
    today = date.today()
    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)

    base_filters = (
        Payment.status == "succeeded",
        Payment.amount_cents > 0,
        Payment.kind.in_(_BONUS_PAYMENT_KINDS_FOR_STATS),
    )

    r = await session.execute(
        select(func.sum(Payment.amount_cents)).select_from(Payment).where(
            *base_filters,
            func.date(Payment.created_at) == today,
        )
    )
    day = float((r.scalar() or 0) / 100.0)

    r = await session.execute(
        select(func.sum(Payment.amount_cents)).select_from(Payment).where(
            *base_filters,
            func.date(Payment.created_at) >= week_start,
        )
    )
    week = float((r.scalar() or 0) / 100.0)

    r = await session.execute(
        select(func.sum(Payment.amount_cents)).select_from(Payment).where(
            *base_filters,
            func.date(Payment.created_at) >= month_start,
        )
    )
    month = float((r.scalar() or 0) / 100.0)

    r = await session.execute(
        select(func.sum(Payment.amount_cents)).select_from(Payment).where(*base_filters)
    )
    total = float((r.scalar() or 0) / 100.0)
    return {"day": day, "week": week, "month": month, "total": total}


async def backfill_revenue_from_payments(session: AsyncSession) -> dict[str, int]:
    """
    Синхронизировать Revenue из успешных платежей (для старых записей до авто-записи в webhook).
    Добавляет Revenue только для платежей, у которых ещё нет записи (по payment_id).
    """
    added = 0
    skipped = 0
    r = await session.execute(
        select(Payment)
        .where(
            Payment.status == "succeeded",
            Payment.amount_cents > 0,
            Payment.kind.in_(["topup", "subscription", "subscription_renewal"]),
        )
    )
    payments = r.scalars().all()
    existing_payment_ids: set[int] = set()
    try:
        r2 = await session.execute(select(Revenue.payment_id).where(Revenue.payment_id.isnot(None)))
        existing_payment_ids = {row[0] for row in r2.all()}
    except Exception:
        pass  # payment_id column may not exist before migration 013
    for p in payments:
        if p.id in existing_payment_ids:
            skipped += 1
            continue
        dt = p.created_at or datetime.utcnow()
        period_date = dt.date() if hasattr(dt, "date") else date.today()
        amount_rub = p.amount_cents / 100.0
        session.add(Revenue(period_date=period_date, amount=amount_rub, payment_id=p.id))
        existing_payment_ids.add(p.id)
        added += 1
    if added:
        await session.commit()
    return {"added": added, "skipped": skipped, "total_processed": len(payments)}


async def _token_cost_for_period(session: AsyncSession, start_d: date, end_d: date) -> float:
    """Сумма токенов в рублях за период с fallback на cost_usd*rate."""
    from datetime import datetime as dt
    start_dt = dt.combine(start_d, dt.min.time())
    end_dt = dt.combine(end_d, dt.max.time())
    rate = await get_exchange_rate(session)
    effective_cost = case(
        (TokenUsage.cost_rub > 0, TokenUsage.cost_rub),
        (TokenUsage.cost_usd > 0, TokenUsage.cost_usd * rate),
        else_=0.0,
    )
    r = await session.execute(
        select(func.coalesce(func.sum(effective_cost), 0)).select_from(TokenUsage).where(
            TokenUsage.created_at >= start_dt,
            TokenUsage.created_at <= end_dt,
        )
    )
    return float(r.scalar() or 0)


async def _commission_by_date_from_payments(
    session: AsyncSession,
    start_d: date | None = None,
    end_d: date | None = None,
) -> dict[date, float]:
    """Комиссия ЮKassa по платежам: приоритет точным данным вебхука, fallback на %."""
    rate = float(get_settings().YOOKASSA_COMMISSION_PERCENT or 0)
    q = select(Payment).where(
        Payment.status == "succeeded",
        Payment.amount_cents > 0,
        Payment.kind.in_(("topup", "subscription", "subscription_renewal")),
    )
    if start_d is not None:
        q = q.where(Payment.created_at >= datetime.combine(start_d, datetime.min.time()))
    if end_d is not None:
        q = q.where(Payment.created_at <= datetime.combine(end_d, datetime.max.time()))
    r = await session.execute(q)
    out: dict[date, float] = {}
    yk_ready = False
    yk_module = None
    yk_loaded = False
    metadata_updated = False

    for payment in r.scalars().all():
        raw_dt = payment.created_at
        if hasattr(raw_dt, "date"):
            day = raw_dt.date()
        else:
            try:
                day = date.fromisoformat(str(raw_dt)[:10])
            except (TypeError, ValueError):
                continue
        commission_rub = None
        income_rub = None
        if payment.metadata_json:
            try:
                meta = json.loads(payment.metadata_json)
                if isinstance(meta, dict):
                    raw_commission = meta.get("commission_rub")
                    raw_income = meta.get("income_amount_rub")
                    if raw_commission is not None:
                        commission_rub = float(raw_commission)
                    if raw_income is not None:
                        income_rub = float(raw_income)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if commission_rub is None and income_rub is not None:
            gross_rub = float(payment.amount_cents or 0) / 100.0
            commission_rub = round(max(0.0, gross_rub - income_rub), 2)
        if commission_rub is None and payment.yookassa_payment_id:
            try:
                # Lazy one-time YooKassa init only when needed.
                if not yk_loaded:
                    yk_loaded = True
                    settings = get_settings()
                    if settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
                        from yookassa import Configuration, Payment as YooPayment
                        Configuration.configure(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
                        yk_ready = True
                        yk_module = YooPayment
                if yk_ready and yk_module is not None:
                    remote_payment = yk_module.find_one(payment.yookassa_payment_id)
                    remote_amount = float(getattr(getattr(remote_payment, "amount", None), "value", 0) or 0)
                    remote_income = float(getattr(getattr(remote_payment, "income_amount", None), "value", 0) or 0)
                    if remote_income > 0 and remote_amount > 0:
                        income_rub = remote_income
                        commission_rub = round(max(0.0, remote_amount - remote_income), 2)
                        _meta = {}
                        if payment.metadata_json:
                            try:
                                parsed_meta = json.loads(payment.metadata_json)
                                if isinstance(parsed_meta, dict):
                                    _meta = parsed_meta
                            except (TypeError, ValueError, json.JSONDecodeError):
                                _meta = {}
                        _meta["income_amount_rub"] = income_rub
                        _meta["commission_rub"] = commission_rub
                        payment.metadata_json = json.dumps(_meta, ensure_ascii=False)
                        metadata_updated = True
            except Exception as exc:
                logger.warning("Failed to fetch YooKassa payment fee for %s: %s", payment.yookassa_payment_id, exc)
        if commission_rub is None:
            if rate <= 0:
                commission_rub = 0.0
            else:
                gross_rub = float(payment.amount_cents or 0) / 100.0
                commission_rub = round(gross_rub * (rate / 100.0), 2)
        out[day] = round(float(out.get(day, 0.0)) + float(commission_rub or 0.0), 2)
    if metadata_updated:
        await session.flush()
    return out


async def _backfill_missing_token_costs(session: AsyncSession, rate: float, limit: int = 5000) -> int:
    """
    Заполнить стоимость в старых token_usage, где стоимость не была рассчитана,
    но total_tokens уже есть.
    """
    r = await session.execute(
        select(TokenUsage)
        .where(
            TokenUsage.error.is_(False),
            TokenUsage.total_tokens > 0,
            or_(TokenUsage.cost_rub <= 0, TokenUsage.cost_usd <= 0),
        )
        .order_by(TokenUsage.created_at.asc())
        .limit(limit)
    )
    rows = r.scalars().all()
    updated = 0
    for t in rows:
        pt = int(t.prompt_tokens or 0)
        ct = int(t.completion_tokens or 0)
        total = int(t.total_tokens or 0)
        if total > 0 and pt == 0 and ct == 0:
            pt = total
            t.prompt_tokens = pt
            t.completion_tokens = 0
        usd, rub = calculate_cost(
            provider=t.provider or "openai",
            model=t.model or "unknown",
            prompt_tokens=pt,
            completion_tokens=ct,
            cached_tokens=int(t.cached_tokens or 0),
            exchange_rate=rate,
        )
        if usd > 0 or rub > 0:
            t.cost_usd = usd
            t.cost_rub = rub
            updated += 1
    if updated:
        await session.commit()
    return updated


async def get_expenses_totals(session: AsyncSession) -> dict[str, Any]:
    """Затраты за день, неделю, месяц, всего - по категориям и сумма. Токены из TokenUsage."""
    rate = await get_exchange_rate(session)
    await _backfill_missing_token_costs(session, rate=rate, limit=2000)
    today = date.today()
    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)
    categories = ("commission", "advertising", "taxes", "tokens")
    manual_categories = ("commission", "advertising", "taxes")

    async def _from_expense_table(period_start: date | None, period_end: date | None = None):
        q = select(Expense.category, func.coalesce(func.sum(Expense.amount), 0)).select_from(Expense)
        if period_start is not None:
            q = q.where(Expense.period_date >= period_start)
        if period_end is not None:
            q = q.where(Expense.period_date <= period_end)
        q = q.group_by(Expense.category)
        r = await session.execute(q)
        return {row[0]: float(row[1]) for row in r.all()}

    day = await _from_expense_table(today, today)
    week = await _from_expense_table(week_start, today)
    month = await _from_expense_table(month_start, today)
    total_exp = await _from_expense_table(None)

    for c in categories:
        if c not in day:
            day[c] = 0.0
        if c not in week:
            week[c] = 0.0
        if c not in month:
            month[c] = 0.0
        if c not in total_exp:
            total_exp[c] = 0.0

    # Fallback: если комиссии не записаны в Expense (старые/пропущенные webhook),
    # показываем их расчетно из успешных платежей YooKassa.
    if float(day.get("commission", 0) or 0) <= 0:
        day["commission"] = round(sum((await _commission_by_date_from_payments(session, today, today)).values()), 2)
    if float(week.get("commission", 0) or 0) <= 0:
        week["commission"] = round(sum((await _commission_by_date_from_payments(session, week_start, today)).values()), 2)
    if float(month.get("commission", 0) or 0) <= 0:
        month["commission"] = round(sum((await _commission_by_date_from_payments(session, month_start, today)).values()), 2)
    if float(total_exp.get("commission", 0) or 0) <= 0:
        total_exp["commission"] = round(sum((await _commission_by_date_from_payments(session, None, None)).values()), 2)

    day["tokens"] = await _token_cost_for_period(session, today, today)
    week["tokens"] = await _token_cost_for_period(session, week_start, today)
    month["tokens"] = await _token_cost_for_period(session, month_start, today)
    effective_cost = case(
        (TokenUsage.cost_rub > 0, TokenUsage.cost_rub),
        (TokenUsage.cost_usd > 0, TokenUsage.cost_usd * rate),
        else_=0.0,
    )
    r = await session.execute(select(func.coalesce(func.sum(effective_cost), 0)).select_from(TokenUsage))
    total_exp["tokens"] = float(r.scalar() or 0)

    def _tot(d: dict[str, float]) -> float:
        return sum(d.values())

    return {
        "day": {"by_category": day, "total": _tot(day)},
        "week": {"by_category": week, "total": _tot(week)},
        "month": {"by_category": month, "total": _tot(month)},
        "total": {"by_category": total_exp, "total": _tot(total_exp)},
    }


async def get_expenses_by_category_for_chart(session: AsyncSession, period: str = "month") -> list[dict]:
    """Затраты по категориям для графика (за выбранный период)."""
    totals = await get_expenses_totals(session)
    data = totals.get(period, totals["month"])
    by_cat = data["by_category"]
    order = ("commission", "advertising", "taxes", "tokens")
    return [{"category": k, "label": EXPENSE_CATEGORY_LABELS.get(k, k), "amount": by_cat.get(k, 0)} for k in order]


async def add_expense_entry(
    session: AsyncSession, period_date: date, category: str, amount: float
) -> bool:
    """Добавить запись о затратах (комиссии, реклама, налоги; токены не вводятся вручную)."""
    if category not in ("commission", "advertising", "taxes"):
        return False
    e = Expense(period_date=period_date, category=category, amount=amount)
    session.add(e)
    await session.flush()
    return True


async def set_expense_for_date(
    session: AsyncSession, period_date: date, category: str, amount: float
) -> bool:
    """Установить сумму затрат за дату по категории (заменяет все записи за эту дату+категорию). Только ручные категории."""
    if category not in ("commission", "advertising", "taxes"):
        return False
    from sqlalchemy import delete
    await session.execute(delete(Expense).where(Expense.period_date == period_date, Expense.category == category))
    if amount > 0:
        session.add(Expense(period_date=period_date, category=category, amount=amount))
    await session.flush()
    return True


async def get_token_costs_by_date(session: AsyncSession, start_d: date, end_d: date) -> dict[str, float]:
    """Затраты на токены по дням с fallback на cost_usd*rate."""
    from datetime import datetime as dt
    start_dt = dt.combine(start_d, dt.min.time())
    end_dt = dt.combine(end_d, dt.max.time())
    rate = await get_exchange_rate(session)
    effective_cost = case(
        (TokenUsage.cost_rub > 0, TokenUsage.cost_rub),
        (TokenUsage.cost_usd > 0, TokenUsage.cost_usd * rate),
        else_=0.0,
    )
    r = await session.execute(
        select(func.date(TokenUsage.created_at), func.coalesce(func.sum(effective_cost), 0))
        .select_from(TokenUsage)
        .where(
            TokenUsage.created_at >= start_dt,
            TokenUsage.created_at <= end_dt,
        )
        .group_by(func.date(TokenUsage.created_at))
    )
    by_date = {}
    for row in r.all():
        k = row[0]
        key = k.isoformat() if hasattr(k, "isoformat") else str(k)
        by_date[key] = float(row[1])
    return by_date


async def get_expenses_table_data(
    session: AsyncSession, year: int, month: int
) -> list[dict[str, Any]]:
    """Данные для таблицы финансов: по дням месяца - комиссии, реклама, налоги (из Expense), токены (авто из History)."""
    from calendar import monthrange
    start_d = date(year, month, 1)
    _, last = monthrange(year, month)
    end_d = date(year, month, last)

    r = await session.execute(
        select(Expense.period_date, Expense.category, func.sum(Expense.amount))
        .select_from(Expense)
        .where(
            Expense.period_date >= start_d,
            Expense.period_date <= end_d,
            Expense.category.in_(("commission", "advertising", "taxes")),
        )
        .group_by(Expense.period_date, Expense.category)
    )
    by_date_cat: dict[date, dict[str, float]] = {}
    for (d, cat, amt) in r.all():
        if d not in by_date_cat:
            by_date_cat[d] = {"commission": 0.0, "advertising": 0.0, "taxes": 0.0}
        by_date_cat[d][cat] = float(amt)

    token_by_date = await get_token_costs_by_date(session, start_d, end_d)
    auto_commission_by_date = await _commission_by_date_from_payments(session, start_d, end_d)

    result = []
    for i in range(1, last + 1):
        d = date(year, month, i)
        iso = d.isoformat()
        row = by_date_cat.get(d, {"commission": 0.0, "advertising": 0.0, "taxes": 0.0})
        commission_val = float(row.get("commission", 0.0) or 0.0)
        if commission_val <= 0:
            commission_val = float(auto_commission_by_date.get(d, 0.0) or 0.0)
        result.append({
            "date": iso,
            "commission": commission_val,
            "advertising": row.get("advertising", 0.0),
            "taxes": row.get("taxes", 0.0),
            "tokens": token_by_date.get(iso, 0.0),
        })
    return result


def _token_usage_text_category_sql():
    """Текстовые ИИ-запросы для графиков токенов: таро (включая tarot_*), гороскоп, натальная, сонник, нумерология."""
    return or_(
        TokenUsage.feature_type.in_(
            ("dream", "numerology", "horoscope", "natal_chart", "astrology", "tarot", "tarot_legacy")
        ),
        TokenUsage.feature_type.like("tarot_%"),
    )


async def get_tokens_series(session: AsyncSession, days: int = 30) -> tuple[list[dict], list[dict]]:
    """Токены по дням: текстовые (tarot, dream, numerology) и визуальные (face, palm, compatibility)."""
    start = datetime.utcnow() - timedelta(days=days)
    # Текстовые - из TokenUsage
    r = await session.execute(
        select(func.date(TokenUsage.created_at), func.sum(TokenUsage.total_tokens))
        .where(
            TokenUsage.created_at >= start,
            _token_usage_text_category_sql(),
            TokenUsage.error.is_(False),
        )
        .group_by(func.date(TokenUsage.created_at))
    )
    text_by_date = {row[0]: row[1] for row in r.all()}
    # Визуальные - всё остальное (face, palm, compatibility и т.д.)
    r = await session.execute(
        select(func.date(TokenUsage.created_at), func.sum(TokenUsage.total_tokens))
        .where(
            TokenUsage.created_at >= start,
            ~_token_usage_text_category_sql(),
            TokenUsage.error.is_(False),
        )
        .group_by(func.date(TokenUsage.created_at))
    )
    vision_by_date = {row[0]: row[1] for row in r.all()}
    result_text = []
    result_vision = []
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        key = date.fromisoformat(d)
        # support both date and str keys (pg vs sqlite)
        t = text_by_date.get(key) or text_by_date.get(d) or 0
        v = vision_by_date.get(key) or vision_by_date.get(d) or 0
        result_text.append({"date": d, "tokens": int(t)})
        result_vision.append({"date": d, "tokens": int(v)})
    return result_text, result_vision


async def get_tokens_totals(session: AsyncSession) -> dict[str, Any]:
    """Токены за день, неделю, месяц, всего; текстовые (tarot,dream,numerology) и визуальные. Источник: TokenUsage."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)
    text_filter = _token_usage_text_category_sql()
    vision_filter = ~_token_usage_text_category_sql()
    no_error = TokenUsage.error.is_(False)

    def _sum_tokens(period_filter, feat_filter=None):
        q = select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).select_from(TokenUsage).where(
            period_filter, no_error
        )
        if feat_filter is not None:
            q = q.where(feat_filter)
        return q

    r = await session.execute(_sum_tokens(TokenUsage.created_at >= today_start))
    day_all = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= week_start))
    week_all = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= month_start))
    month_all = int(r.scalar() or 0)
    r = await session.execute(select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).select_from(TokenUsage).where(no_error))
    total_all = int(r.scalar() or 0)

    r = await session.execute(_sum_tokens(TokenUsage.created_at >= today_start, text_filter))
    day_text = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= week_start, text_filter))
    week_text = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= month_start, text_filter))
    month_text = int(r.scalar() or 0)
    r = await session.execute(select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).select_from(TokenUsage).where(no_error, text_filter))
    total_text = int(r.scalar() or 0)

    r = await session.execute(_sum_tokens(TokenUsage.created_at >= today_start, vision_filter))
    day_vision = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= week_start, vision_filter))
    week_vision = int(r.scalar() or 0)
    r = await session.execute(_sum_tokens(TokenUsage.created_at >= month_start, vision_filter))
    month_vision = int(r.scalar() or 0)
    r = await session.execute(select(func.coalesce(func.sum(TokenUsage.total_tokens), 0)).select_from(TokenUsage).where(no_error, vision_filter))
    total_vision = int(r.scalar() or 0)

    return {
        "day": {"all": day_all, "text": day_text, "vision": day_vision},
        "week": {"all": week_all, "text": week_text, "vision": week_vision},
        "month": {"all": month_all, "text": month_text, "vision": month_vision},
        "total": {"all": total_all, "text": total_text, "vision": total_vision},
    }


async def get_usage_by_type(session: AsyncSession) -> dict[str, int]:
    """Количество использований по разделам: Таро, Сканер, Сны, Нумерология."""
    r = await session.execute(select(History.type, func.count(History.id)).group_by(History.type))
    return {str(row[0].value): row[1] for row in r.all()}


def _time_bucket_key(ts: datetime, now_utc: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ts >= now_utc - timedelta(days=1):
        return "day"
    if ts >= now_utc - timedelta(days=7):
        return "week"
    if ts >= now_utc - timedelta(days=30):
        return "month"
    return "older"


async def get_horoscope_stats(session: AsyncSession) -> dict[str, Any]:
    """Horoscope module removed from TARO; return empty stats for admin compatibility."""
    _ = session
    empty = {"day": 0, "week": 0, "month": 0}
    return {
        "views": dict(empty),
        "shares": dict(empty),
        "reminders_set": dict(empty),
        "active_reminders": 0,
        "period_views": dict(empty),
        "period_shares": dict(empty),
        "sign_popularity": [],
        "blocks_popularity": [],
        "unique_texts_30d": 0,
    }


def _bot_stopped_label(member_status: str | None) -> str:
    st = (member_status or "").strip().lower()
    if st == "kicked":
        return "заблокировал бота"
    if st == "left":
        return "вышел из чата"
    if st == "banned":
        return "нет доступа к чату"
    if st:
        return f"статус: {st}"
    return "остановил бота"


async def get_users_list(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    visit_segment: str | None = None,
    visit_sort: str | None = None,
    bot_filter: str | None = None,
) -> tuple[list[dict], int]:
    """Список пользователей с профилем (имя, пол, возраст, подписка)."""
    valid_segments = {"day", "week", "month", "year"}
    normalized_segment = (visit_segment or "").strip().lower()
    if normalized_segment not in valid_segments:
        normalized_segment = ""
    normalized_visit_sort = (visit_sort or "").strip().lower()
    if normalized_visit_sort not in {"desc", "asc"}:
        normalized_visit_sort = ""
    normalized_bot = (bot_filter or "").strip().lower()
    if normalized_bot not in {"stopped", "active"}:
        normalized_bot = ""

    now_utc = datetime.now(timezone.utc)
    day_cutoff = now_utc - timedelta(days=1)
    week_cutoff = now_utc - timedelta(days=7)
    month_cutoff = now_utc - timedelta(days=30)
    year_cutoff = now_utc - timedelta(days=365)

    history_last_subq = (
        select(
            History.user_id.label("user_id"),
            func.max(History.created_at).label("last_history_at"),
        )
        .group_by(History.user_id)
        .subquery()
    )
    history_last_expr = history_last_subq.c.last_history_at
    seen_last_expr = User.last_seen_at
    latest_touch_expr = case(
        (history_last_expr.is_(None), seen_last_expr),
        (seen_last_expr.is_(None), history_last_expr),
        (history_last_expr >= seen_last_expr, history_last_expr),
        else_=seen_last_expr,
    )
    last_activity_expr = func.coalesce(latest_touch_expr, User.created_at)

    q = (
        select(User, last_activity_expr.label("last_activity_at"))
        .outerjoin(history_last_subq, history_last_subq.c.user_id == User.telegram_id)
    )
    count_q = (
        select(func.count())
        .select_from(User)
        .outerjoin(history_last_subq, history_last_subq.c.user_id == User.telegram_id)
    )
    if search:
        like = f"%{search}%"
        q = q.where(
            User.username.ilike(like) | User.full_name.ilike(like) | (User.telegram_id.cast(String).ilike(like))
        )
        count_q = count_q.where(
            User.username.ilike(like) | User.full_name.ilike(like) | (User.telegram_id.cast(String).ilike(like))
        )

    if normalized_segment == "day":
        q = q.where(last_activity_expr >= day_cutoff)
        count_q = count_q.where(last_activity_expr >= day_cutoff)
    elif normalized_segment == "week":
        q = q.where(last_activity_expr >= week_cutoff, last_activity_expr < day_cutoff)
        count_q = count_q.where(last_activity_expr >= week_cutoff, last_activity_expr < day_cutoff)
    elif normalized_segment == "month":
        q = q.where(last_activity_expr >= month_cutoff, last_activity_expr < week_cutoff)
        count_q = count_q.where(last_activity_expr >= month_cutoff, last_activity_expr < week_cutoff)
    elif normalized_segment == "year":
        q = q.where(last_activity_expr >= year_cutoff, last_activity_expr < month_cutoff)
        count_q = count_q.where(last_activity_expr >= year_cutoff, last_activity_expr < month_cutoff)

    if normalized_bot == "stopped":
        q = q.where(User.bot_stopped_at.isnot(None))
        count_q = count_q.where(User.bot_stopped_at.isnot(None))
    elif normalized_bot == "active":
        q = q.where(User.bot_stopped_at.is_(None))
        count_q = count_q.where(User.bot_stopped_at.is_(None))

    r = await session.execute(count_q)
    total = r.scalar() or 0
    if normalized_visit_sort == "desc":
        q = q.order_by(last_activity_expr.desc(), User.created_at.desc())
    elif normalized_visit_sort == "asc":
        q = q.order_by(last_activity_expr.asc(), User.created_at.asc())
    else:
        q = q.order_by(User.created_at.desc())
    r = await session.execute(q.offset(skip).limit(limit))
    user_rows = r.all()
    users = [row[0] for row in user_rows]
    user_ids = [u.telegram_id for u in users]
    total_topup_by_user: dict[int, int] = {}
    if user_ids:
        topup_kinds = ("topup", "subscription", "subscription_renewal")
        topup_q = (
            select(
                Payment.user_id,
                func.coalesce(
                    func.sum(
                        case(
                            (and_(Payment.amount_cents > 0, Payment.kind.in_(topup_kinds)), Payment.amount_cents),
                            else_=0,
                        )
                    ),
                    0,
                ).label("topup"),
            )
            .where(Payment.user_id.in_(user_ids), Payment.status == "succeeded")
            .group_by(Payment.user_id)
        )
        topup_r = await session.execute(topup_q)
        for row in topup_r.all():
            total_topup_by_user[int(row.user_id)] = int(row.topup or 0)
    last_activity_by_user: dict[int, datetime | None] = {}
    for u, last_activity in user_rows:
        dt_val: datetime | None = last_activity
        if dt_val is not None and dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        last_activity_by_user[int(u.telegram_id)] = dt_val
    # Автообновление username/full_name из Telegram (до 5 пользователей с пустыми данными за запрос)
    sync_count = 0
    for u in users:
        if sync_count < 5 and not (u.username or u.full_name):
            try:
                res = await sync_user_from_telegram(session, u.telegram_id)
                if res.get("ok"):
                    await session.flush()
                    await session.refresh(u)
                    sync_count += 1
            except Exception:
                pass
    out = []
    for u in users:
        last_activity_at = last_activity_by_user.get(int(u.telegram_id))
        visit_key = "older"
        visit_label = "старше года"
        if last_activity_at:
            if last_activity_at >= day_cutoff:
                visit_key, visit_label = "day", "день"
            elif last_activity_at >= week_cutoff:
                visit_key, visit_label = "week", "неделя"
            elif last_activity_at >= month_cutoff:
                visit_key, visit_label = "month", "месяц"
            elif last_activity_at >= year_cutoff:
                visit_key, visit_label = "year", "год"

        balance_cents = getattr(u, "balance_cents", 0) or 0
        total_topup_cents = total_topup_by_user.get(int(u.telegram_id), 0)
        # Пользователь «сейчас в приложении», если активность в последние 3 минуты
        last_act = last_activity_by_user.get(int(u.telegram_id))
        is_currently_active = bool(
            last_act and (now_utc - last_act).total_seconds() < 180
        )
        bot_stopped_at = getattr(u, "bot_stopped_at", None)
        bot_member_status = getattr(u, "bot_member_status", None) or ""
        out.append({
            "visit_segment": visit_key,
            "visit_segment_label": visit_label,
            "telegram_id": u.telegram_id,
            "is_currently_active": is_currently_active,
            "total_topup_cents": total_topup_cents,
            "username": u.username,
            "full_name": u.full_name,
            "name": u.full_name or u.username,
            "profile_name": u.full_name or u.username,
            "birth_city": None,
            "status": u.status,
            "subscription_end_date": u.subscription_end_date.isoformat() if u.subscription_end_date else None,
            "trial_ends_at": u.trial_ends_at.isoformat() if u.trial_ends_at else None,
            "gender": None,
            "age": None,
            "balance_cents": balance_cents,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "bot_stopped_at": bot_stopped_at.isoformat() if bot_stopped_at else None,
            "bot_member_status": bot_member_status,
            "bot_stopped_detail": _bot_stopped_label(bot_member_status) if bot_stopped_at else "",
        })
    return out, total


# Типы history, которые дублируют учёт в token_usage (новые API пишут токены, не history).
_HISTORY_TYPES_SKIP_WHEN_USING_TOKEN_USAGE: frozenset[str] = frozenset(
    {
        HistoryType.TAROT.value,
        HistoryType.VISION.value,
        HistoryType.DREAM.value,
        HistoryType.NUMEROLOGY.value,
    }
)

_TAROT_SPREAD_LABELS: dict[str, str] = {
    "single": "карта дня",
    "three_cards": "3 карты",
    "financial": "финансы (5 карт)",
    "six_cards": "отношения (6 карт)",
    "ten_cards": "кельтский крест",
}


def _usage_label_token_feature(ft: str) -> str:
    """Подпись для TokenUsage.feature_type по продуктовой сетке ASTROV."""
    x = (ft or "").strip().lower()
    if not x:
        return "Неизвестно"
    direct: dict[str, str] = {
        "horoscope": "Гороскоп (день / неделя / месяц): генерация ИИ",
        "natal_chart": "Натальная карта",
        "astrology": "Гороскоп / натальная карта (старый тип в логах до разделения)",
        "dream": "Сонник",
        "numerology": "Матрица судьбы / нумерология",
        "numerology_compatibility": "Совместимость: нумерологический метод",
        "life_path_compatibility": "Совместимость: числа жизненного пути",
        "synastry_compatibility": "Совместимость: астрологический метод (синастрия)",
        "face": "Анализ: портрет",
        "face_localization": "Анализ: портрет (детекция лица)",
        "palm": "Анализ: хиромантия",
        "palm_localization": "Анализ: хиромантия (детекция)",
        "compatibility": "Анализ: совместимость по фото",
        "compatibility_localization": "Анализ: совместимость по фото (детекция)",
        "palm_comparison": "Анализ: сравнение ладоней",
        "horoscope_reminder_teaser": "Гороскоп: тизер к напоминанию",
        "tarot": "Таро (старый учёт)",
        "tarot_legacy": "Таро: старый эндпоинт",
        "tarot_six_cards_realign": "Таро: служебная правка расклада «отношения»",
        "tarot_answer_check": "Таро: проверка ответа",
        "tarot_card_backfill": "Таро: дозаполнение толкования карты",
        "tarot_card_vision": "Таро: описание изображения карты",
        "tarot_tarologist_chat": "Таро: диалог перед раскладом",
        "tarot_followup_chat": "Таро: уточнение по раскладу",
    }
    if x in direct:
        return direct[x]
    if x.startswith("tarot_realign_"):
        sp = x.replace("tarot_realign_", "", 1)
        human = _TAROT_SPREAD_LABELS.get(sp, sp)
        return f"Таро: правка под вопрос ({human})"
    if x.startswith("tarot_"):
        sp = x[6:]
        if sp in _TAROT_SPREAD_LABELS:
            return f"Таро: {_TAROT_SPREAD_LABELS[sp]}"
        return f"Таро: {sp}"
    return f"ИИ: {ft}"


def _usage_label_history_feature(hk: str) -> str:
    """Подпись для ключа из history (без префикса tu:)."""
    k = (hk or "").strip().lower()
    if not k:
        return "Неизвестно"
    hm: dict[str, str] = {
        "natal": "Натальная карта (маркер / оплата)",
        "keys": "Ключи",
        "shadow": "Тень",
        "forecast": "Прогноз (день / месяц / год), не гороскоп ленты",
        "horoscope_view": "Гороскоп: просмотр",
        "horoscope_share": "Гороскоп: шаринг",
        "horoscope_remind_set": "Гороскоп: напоминание вкл.",
        "horoscope_remind_cancel": "Гороскоп: напоминание откл.",
    }
    if k in hm:
        return hm[k]
    if k.startswith("horoscope_planet_detail"):
        return "Гороскоп: деталь планеты"
    if k.startswith("horoscope_"):
        tail = k.replace("horoscope_", "", 1)
        return f"Гороскоп: {tail}"
    return hk


def _usage_display_label_for_row_key(raw_key: str) -> str:
    rk = (raw_key or "").strip()
    if rk.startswith("tu:"):
        return _usage_label_token_feature(rk[3:])
    return _usage_label_history_feature(rk.lower())


def _history_row_feature_key(type_str: str | None, request_content: str | None) -> str:
    """Ключ сервиса по строковому типу из БД и request_content."""
    t = (type_str or "").strip().lower()
    req = (request_content or "").strip()
    if t == HistoryType.FORECAST.value and req.startswith("horoscope_"):
        return req.split(":", 1)[0].strip() or t
    return t


async def get_user_service_usage_by_day(
    session: AsyncSession,
    telegram_id: int,
    *,
    limit_days: int = 120,
) -> list[dict[str, Any]]:
    """Сервисы по дням (UTC): token_usage (основной учёт ИИ) + history (без дублей с токенами).

    Новые эндпоинты пишут расход в token_usage; гороскоп (просмотр, шаринг, напоминания) и часть
    оплат/прогнозов остаётся в history.
    """
    limit_days = max(1, min(int(limit_days), 366))
    since = datetime.now(timezone.utc) - timedelta(days=limit_days)

    counts: dict[tuple[date, str], int] = defaultdict(int)

    tu = await session.execute(
        select(TokenUsage.created_at, TokenUsage.feature_type).where(
            TokenUsage.user_id == telegram_id,
            TokenUsage.created_at >= since,
        )
    )
    for created_at, feature_type in tu.all():
        if created_at is None:
            continue
        dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        day_key = dt.date()
        ft = (feature_type or "").strip() or "unknown"
        fk = f"tu:{ft}"
        counts[(day_key, fk)] += 1

    rh = await session.execute(
        select(
            History.created_at,
            cast(History.type, String).label("type_str"),
            History.request_content,
        ).where(
            History.user_id == telegram_id,
            History.created_at >= since,
        )
    )
    for created_at, type_str, req in rh.all():
        if created_at is None:
            continue
        dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        day_key = dt.date()
        ts = type_str if isinstance(type_str, str) else (str(type_str) if type_str is not None else "")
        fk = _history_row_feature_key(ts, req)
        if not fk:
            fk = "unknown"
        if fk in _HISTORY_TYPES_SKIP_WHEN_USING_TOKEN_USAGE:
            continue
        counts[(day_key, fk)] += 1

    by_day: dict[date, list[tuple[str, int]]] = defaultdict(list)
    for (d_key, fk), cnt in counts.items():
        by_day[d_key].append((fk, cnt))

    out: list[dict[str, Any]] = []
    for day_key in sorted(by_day.keys(), reverse=True):
        items_raw = by_day[day_key]
        items: list[dict[str, Any]] = []
        total = 0
        for fk, cnt in sorted(items_raw, key=lambda x: (-x[1], x[0])):
            total += cnt
            label = _usage_display_label_for_row_key(fk)
            items.append(
                {
                    "feature": fk,
                    "label": label,
                    "count": cnt,
                }
            )
        out.append(
            {
                "day": day_key.isoformat(),
                "day_label": day_key.strftime("%d.%m.%Y"),
                "total": total,
                "rows": items,
            }
        )
    return out


async def get_user_for_edit(session: AsyncSession, telegram_id: int) -> dict | None:
    """Один пользователь для формы редактирования подписки + учёт баланса и операций."""
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    u = r.scalar_one_or_none()
    if not u:
        return None
    balance_cents = getattr(u, "balance_cents", 0) or 0

    # Топ-апы и списания
    real_topup_kinds = ("topup", "subscription", "subscription_renewal")
    r = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(Payment.amount_cents > 0, Payment.kind.in_(real_topup_kinds)),
                            Payment.amount_cents,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(Payment.amount_cents > 0, Payment.kind.in_(_BONUS_PAYMENT_KINDS_FOR_STATS)),
                            Payment.amount_cents,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(case((Payment.amount_cents < 0, func.abs(Payment.amount_cents)), else_=0)), 0),
        ).select_from(Payment).where(Payment.user_id == telegram_id, Payment.status == "succeeded")
    )
    row = r.one_or_none() or (0, 0, 0)
    total_topup_cents = int(row[0] or 0)
    total_bonus_cents = int(row[1] or 0)
    total_spent_cents = int(row[2] or 0)

    r = await session.execute(
        select(Payment)
        .where(Payment.user_id == telegram_id)
        .order_by(Payment.created_at.desc())
        .limit(100)
    )
    payments = r.scalars().all()
    payment_rows = [
        {
            "created_at": p.created_at.strftime("%d.%m.%Y %H:%M") if p.created_at else "-",
            "kind": p.kind,
            "kind_label": _payment_kind_label_ru(p.kind or ""),
            "amount_cents": p.amount_cents,
            "status": p.status,
        }
        for p in payments
    ]

    try:
        usage_by_day = await get_user_service_usage_by_day(session, telegram_id)
    except Exception:
        logger.exception("admin: usage_by_day failed for telegram_id=%s", telegram_id)
        usage_by_day = []

    return {
        "telegram_id": u.telegram_id,
        "username": u.username,
        "full_name": u.full_name,
        "status": u.status,
        "referred_by_telegram_id": getattr(u, "referred_by_telegram_id", None),
        "subscription_end_date": u.subscription_end_date.isoformat()[:10] if u.subscription_end_date else "",
        "trial_ends_at": u.trial_ends_at.isoformat()[:10] if u.trial_ends_at else "",
        "balance_cents": balance_cents,
        "total_topup_cents": total_topup_cents,
        "total_bonus_cents": total_bonus_cents,
        "total_spent_cents": total_spent_cents,
        "payments": payment_rows,
        "usage_by_day": usage_by_day,
        "bot_member_status": getattr(u, "bot_member_status", None) or "",
        "bot_stopped_at": u.bot_stopped_at.isoformat() if getattr(u, "bot_stopped_at", None) else "",
        "bot_stopped_detail": _bot_stopped_label(getattr(u, "bot_member_status", None))
        if getattr(u, "bot_stopped_at", None)
        else "",
    }


def _parse_optional_coord(raw: str | float | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


async def add_bonus_balance_for_user(
    session: AsyncSession,
    telegram_id: int,
    amount_cents: int,
    note: str = "",
) -> bool:
    """Начислить пользователю бонусный баланс (учёт отдельно как bonus_admin)."""
    if amount_cents <= 0:
        return False
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if not user:
        return False
    user.balance_cents = int(getattr(user, "balance_cents", 0) or 0) + int(amount_cents)
    meta = {"source": "admin_bonus"}
    note_clean = (note or "").strip()
    if note_clean:
        meta["note"] = note_clean[:500]
    payment = Payment(
        user_id=telegram_id,
        amount_cents=int(amount_cents),
        kind="bonus_admin",
        status="succeeded",
        metadata_json=json.dumps(meta, ensure_ascii=False),
    )
    session.add(payment)
    await session.flush()
    await add_balance_ledger_on_topup(
        session,
        telegram_id=telegram_id,
        amount_cents=int(amount_cents),
        payment_id=payment.id,
    )
    await session.flush()
    return True


async def get_exchange_rate(session: AsyncSession) -> float:
    """Авто-курс USD/RUB (с кешем в admin_settings)."""
    return float(await _auto_get_exchange_rate(session))


async def set_exchange_rate(session: AsyncSession, rate: float) -> None:
    """Совместимость: ручная установка курса в настройках."""
    await _auto_update_exchange_rate(session, rate)


async def get_exchange_rate_updated_at(session: AsyncSession):
    """Дата последнего обновления курса."""
    r = await session.execute(
        select(AdminSetting.updated_at).where(AdminSetting.key == ADMIN_SETTING_USD_RUB).limit(1)
    )
    row = r.one_or_none()
    return row[0] if row else None


def _token_usage_period_bounds(period: str) -> tuple[date, date]:
    """Начало и конец периода для токенов (day, week, month, all)."""
    today = date.today()
    if period == "day":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    if period == "month":
        return today - timedelta(days=29), today
    return date(2000, 1, 1), today


async def get_token_usage_stats(
    session: AsyncSession,
    period: str = "week",
    skip: int = 0,
    limit: int = 100,
    user_id_filter: int | None = None,
    feature_filter: str | None = None,
) -> dict[str, Any]:
    """Агрегаты по token_usage за период: total_rub, total_tokens, daily, by_feature, by_provider, details."""
    rate = await get_exchange_rate(session)
    await _backfill_missing_token_costs(session, rate=rate, limit=5000)
    start_d, end_d = _token_usage_period_bounds(period)
    start_dt = datetime.combine(start_d, datetime.min.time())
    end_dt = datetime.combine(end_d, datetime.max.time())
    effective_cost = case(
        (TokenUsage.cost_rub > 0, TokenUsage.cost_rub),
        (TokenUsage.cost_usd > 0, TokenUsage.cost_usd * rate),
        else_=0.0,
    )
    filters = [
        TokenUsage.created_at >= start_dt,
        TokenUsage.created_at <= end_dt,
    ]
    if user_id_filter is not None:
        filters.append(TokenUsage.user_id == user_id_filter)
    if feature_filter:
        filters.append(TokenUsage.feature_type == feature_filter)

    # Итого рубли и токены
    r = await session.execute(
        select(
            func.coalesce(func.sum(effective_cost), 0),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0),
        ).select_from(TokenUsage).where(*filters)
    )
    row = r.one_or_none() or (0, 0)
    total_rub = float(row[0] or 0)
    total_tokens = int(row[1] or 0) if row else 0

    # По дням
    r = await session.execute(
        select(func.date(TokenUsage.created_at), func.sum(effective_cost), func.sum(TokenUsage.total_tokens))
        .select_from(TokenUsage)
        .where(*filters)
        .group_by(func.date(TokenUsage.created_at))
    )
    by_date = {}
    for row in r.all():
        k = row[0]
        if hasattr(k, "isoformat"):
            key = k
        else:
            try:
                key = date.fromisoformat(str(k)[:10])
            except (ValueError, TypeError):
                key = k
        by_date[key] = {"rub": float(row[1] or 0), "tokens": int(row[2] or 0)}
    daily = []
    d = start_d
    while d <= end_d:
        v = by_date.get(d, {"rub": 0, "tokens": 0})
        daily.append({"date": d.isoformat(), "rub": v["rub"], "tokens": v["tokens"]})
        d += timedelta(days=1)

    # По типу функции
    r = await session.execute(
        select(TokenUsage.feature_type, func.sum(effective_cost), func.sum(TokenUsage.total_tokens))
        .select_from(TokenUsage)
        .where(*filters)
        .group_by(TokenUsage.feature_type)
    )
    by_feature = [{"feature": row[0], "rub": float(row[1]), "tokens": int(row[2])} for row in r.all()]

    # По провайдеру
    r = await session.execute(
        select(TokenUsage.provider, func.sum(effective_cost), func.sum(TokenUsage.total_tokens))
        .select_from(TokenUsage)
        .where(*filters)
        .group_by(TokenUsage.provider)
    )
    by_provider = [{"provider": row[0], "rub": float(row[1]), "tokens": int(row[2])} for row in r.all()]

    # Детали с пагинацией
    details_stmt = (
        select(TokenUsage)
        .where(*filters)
        .order_by(TokenUsage.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    r = await session.execute(details_stmt)
    rows = r.scalars().all()
    details = [
        {
            "id": t.id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "user_id": t.user_id,
            "feature_type": t.feature_type,
            "provider": t.provider,
            "model": t.model,
            "total_tokens": t.total_tokens,
            "cost_rub": round((t.cost_rub if (t.cost_rub or 0) > 0 else (t.cost_usd or 0) * rate), 2),
        }
        for t in rows
    ]

    return {
        "period": period,
        "total_rub": round(total_rub, 2),
        "total_tokens": total_tokens,
        "exchange_rate": round(rate, 4),
        "daily": daily,
        "by_feature": by_feature,
        "by_provider": by_provider,
        "details": details,
    }


async def get_token_usage_details_count(
    session: AsyncSession,
    period: str = "week",
    user_id_filter: int | None = None,
    feature_filter: str | None = None,
) -> int:
    start_d, end_d = _token_usage_period_bounds(period)
    start_dt = datetime.combine(start_d, datetime.min.time())
    end_dt = datetime.combine(end_d, datetime.max.time())
    q = select(func.count()).select_from(TokenUsage).where(
        TokenUsage.created_at >= start_dt,
        TokenUsage.created_at <= end_dt,
    )
    if user_id_filter is not None:
        q = q.where(TokenUsage.user_id == user_id_filter)
    if feature_filter:
        q = q.where(TokenUsage.feature_type == feature_filter)
    r = await session.execute(q)
    return r.scalar() or 0


async def update_user_subscription(
    session: AsyncSession,
    telegram_id: int,
    status: str | None = None,
    subscription_end_date: str | None = None,
    trial_ends_at: str | None = None,
    gift_days: int | None = None,
) -> bool:
    """Обновить статус и даты подписки; gift_days - продлить подписку на N дней от сегодня."""
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if not user:
        return False
    if status is not None:
        user.status = status
    if subscription_end_date is not None:
        from datetime import datetime as dt
        user.subscription_end_date = dt.fromisoformat(subscription_end_date.replace("Z", "+00:00")) if subscription_end_date else None
    if trial_ends_at is not None:
        from datetime import datetime as dt
        user.trial_ends_at = dt.fromisoformat(trial_ends_at.replace("Z", "+00:00")) if trial_ends_at else None
    if gift_days is not None and gift_days > 0:
        from datetime import datetime as dt, timezone
        end = (dt.now(timezone.utc) + timedelta(days=gift_days)).replace(tzinfo=timezone.utc)
        if user.subscription_end_date and user.subscription_end_date > end:
            pass  # не уменьшаем
        else:
            user.subscription_end_date = end
        user.status = "full_access"
    await session.flush()
    return True


async def sync_user_from_telegram(
    session: AsyncSession,
    telegram_id: int,
) -> dict[str, Any]:
    """
    Загружает username/full_name пользователя из Telegram Bot API (getChat) и обновляет запись User.
    Возвращает {"ok": bool, "message": str, "username": str|None, "full_name": str|None}.
    """
    settings = get_settings()
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        return {"ok": False, "message": "TELEGRAM_BOT_TOKEN не задан", "username": None, "full_name": None}
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    if not user:
        return {"ok": False, "message": "Пользователь не найден в БД", "username": None, "full_name": None}
    url = f"https://api.telegram.org/bot{token}/getChat"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"chat_id": telegram_id})
        data = resp.json()
        if not data.get("ok"):
            err = data.get("description", "Unknown error")
            return {"ok": False, "message": f"Telegram API: {err}", "username": None, "full_name": None}
        result = data.get("result", {})
        username = (result.get("username") or "").strip() or None
        first_name = (result.get("first_name") or "").strip()
        last_name = (result.get("last_name") or "").strip()
        full_name = (" ".join(filter(None, [first_name, last_name]))).strip() or None
        await session.execute(
            update(User).where(User.telegram_id == telegram_id).values(username=username, full_name=full_name)
        )
        await session.flush()
        return {
            "ok": True,
            "message": "Данные обновлены из Telegram",
            "username": username,
            "full_name": full_name,
        }
    except httpx.HTTPError as exc:
        logger.warning("sync_user_from_telegram httpx error: %s", exc)
        return {"ok": False, "message": str(exc), "username": None, "full_name": None}
    except Exception as exc:
        logger.exception("sync_user_from_telegram failed: %s", exc)
        return {"ok": False, "message": str(exc), "username": None, "full_name": None}


def _feedback_status_flags(status: str | None) -> tuple[str, str]:
    raw = (status or "").strip().lower()
    if raw == "read_resolved":
        return "read", "resolved"
    if raw == "read_unresolved":
        return "read", "unresolved"
    return "unread", "unresolved"


def _feedback_thread_row_filter(
    *,
    search: str,
    status_filter: str,
) -> Any:
    """Условие на строки feedback для списка веток (одна ветка на пользователя)."""
    clauses: list[Any] = []
    s = (search or "").strip()
    if s:
        like = f"%{s}%"
        user_ids_q = select(User.telegram_id).where(
            or_(
                User.username.ilike(like),
                User.full_name.ilike(like),
                User.telegram_id.cast(String).ilike(like),
            )
        )
        clauses.append(
            Feedback.user_id.in_(
                select(Feedback.user_id)
                .where(or_(Feedback.message.ilike(like), Feedback.user_id.in_(user_ids_q)))
                .distinct()
            )
        )
    sf = (status_filter or "").strip().lower()
    if sf == "unread":
        clauses.append(
            Feedback.user_id.in_(
                select(Feedback.user_id).where(Feedback.status.ilike("unread_%")).distinct()
            )
        )
    elif sf == "read":
        clauses.append(
            Feedback.user_id.in_(
                select(Feedback.user_id).where(Feedback.status.ilike("read_%")).distinct()
            )
        )
    elif sf == "resolved":
        clauses.append(
            Feedback.user_id.in_(
                select(Feedback.user_id).where(Feedback.status == "read_resolved").distinct()
            )
        )
    elif sf == "unresolved":
        clauses.append(
            Feedback.user_id.in_(
                select(Feedback.user_id)
                .where(
                    or_(
                        Feedback.status.ilike("unread_%"),
                        Feedback.status == "read_unresolved",
                    )
                )
                .distinct()
            )
        )
    return and_(*clauses) if clauses else true()


async def get_feedback_list(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    status_filter: str = "",
    search: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Список веток: одна строка на пользователя, сортировка по последнему обращению."""
    row_filter = _feedback_thread_row_filter(search=search, status_filter=status_filter)
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(
                    select(Feedback.user_id).where(row_filter).distinct().subquery()
                )
            )
        ).scalar()
        or 0
    )
    agg = (
        select(
            Feedback.user_id.label("uid"),
            func.max(Feedback.created_at).label("last_at"),
            func.count(Feedback.id).label("msg_count"),
            func.sum(case((Feedback.status.ilike("unread_%"), 1), else_=0)).label("unread_sum"),
        )
        .where(row_filter)
        .group_by(Feedback.user_id)
        .order_by(func.max(Feedback.created_at).desc(), Feedback.user_id.desc())
        .offset(skip)
        .limit(limit)
    )
    page_rows = (await session.execute(agg)).all()
    if not page_rows:
        return [], total

    uids = [int(r.uid) for r in page_rows]
    all_fb = (
        await session.execute(
            select(Feedback)
            .where(Feedback.user_id.in_(uids))
            .order_by(Feedback.user_id, Feedback.created_at.desc(), Feedback.id.desc())
        )
    ).scalars().all()
    latest_by_uid: dict[int, Feedback] = {}
    for f in all_fb:
        uid = int(f.user_id)
        if uid not in latest_by_uid:
            latest_by_uid[uid] = f

    users_rows = (await session.execute(select(User).where(User.telegram_id.in_(uids)))).scalars().all()
    users_map = {int(u.telegram_id): u for u in users_rows}
    attach_totals = (
        await session.execute(
            select(Feedback.user_id, func.count(FeedbackAttachment.id))
            .join(FeedbackAttachment, FeedbackAttachment.feedback_id == Feedback.id)
            .where(Feedback.user_id.in_(uids))
            .group_by(Feedback.user_id)
        )
    ).all()
    attach_thread_map = {int(uid): int(cnt) for uid, cnt in attach_totals}

    out: list[dict[str, Any]] = []
    for r in page_rows:
        uid = int(r.uid)
        latest = latest_by_uid.get(uid)
        if not latest:
            continue
        read_state, resolved_state = _feedback_status_flags(latest.status)
        user = users_map.get(uid)
        unread_n = int(r.unread_sum or 0)
        out.append(
            {
                "user_id": uid,
                "message_count": int(r.msg_count or 0),
                "latest_id": int(latest.id),
                "username": user.username if user else "",
                "full_name": user.full_name if user else "",
                "profile_name": (user.full_name if user else "") or (user.username if user else ""),
                "message": latest.message,
                "created_at": latest.created_at,
                "status": latest.status or "unread_unresolved",
                "read_state": read_state,
                "resolved_state": resolved_state,
                "has_unread_in_thread": unread_n > 0,
                "unread_in_thread": unread_n,
                "attachments_count": attach_thread_map.get(uid, 0),
            }
        )
    return out, total


async def get_feedback_user_thread(session: AsyncSession, telegram_id: int) -> dict[str, Any] | None:
    """Все обращения пользователя по времени (для страницы ветки)."""
    rows = (
        await session.execute(
            select(Feedback)
            .where(Feedback.user_id == int(telegram_id))
            .order_by(Feedback.created_at.asc(), Feedback.id.asc())
        )
    ).scalars().all()
    if not rows:
        return None
    user = (
        await session.execute(select(User).where(User.telegram_id == int(telegram_id)).limit(1))
    ).scalar_one_or_none()
    fids = [int(f.id) for f in rows]
    attach_counts = (
        await session.execute(
            select(FeedbackAttachment.feedback_id, func.count(FeedbackAttachment.id))
            .where(FeedbackAttachment.feedback_id.in_(fids))
            .group_by(FeedbackAttachment.feedback_id)
        )
    ).all()
    attach_map = {int(fid): int(c) for fid, c in attach_counts}
    messages: list[dict[str, Any]] = []
    for f in rows:
        rs, rv = _feedback_status_flags(f.status)
        messages.append(
            {
                "id": int(f.id),
                "message": f.message,
                "created_at": f.created_at,
                "status": f.status or "unread_unresolved",
                "read_state": rs,
                "resolved_state": rv,
                "attachments_count": attach_map.get(int(f.id), 0),
            }
        )
    return {
        "telegram_id": int(telegram_id),
        "user": user,
        "profile": None,
        "messages": messages,
    }


async def get_feedback_details(session: AsyncSession, feedback_id: int) -> dict[str, Any] | None:
    """Feedback details with attachments and admin replies."""
    feedback = (
        await session.execute(select(Feedback).where(Feedback.id == feedback_id).limit(1))
    ).scalar_one_or_none()
    if not feedback:
        return None
    user = (
        await session.execute(select(User).where(User.telegram_id == feedback.user_id).limit(1))
    ).scalar_one_or_none()
    attachments = (
        await session.execute(
            select(FeedbackAttachment)
            .where(FeedbackAttachment.feedback_id == feedback.id)
            .order_by(FeedbackAttachment.created_at.asc(), FeedbackAttachment.id.asc())
        )
    ).scalars().all()
    replies = (
        await session.execute(
            select(FeedbackReply)
            .where(FeedbackReply.feedback_id == feedback.id)
            .order_by(FeedbackReply.created_at.asc(), FeedbackReply.id.asc())
        )
    ).scalars().all()
    read_state, resolved_state = _feedback_status_flags(feedback.status)
    return {
        "feedback": feedback,
        "user": user,
        "profile": None,
        "attachments": attachments,
        "replies": replies,
        "read_state": read_state,
        "resolved_state": resolved_state,
    }


async def set_feedback_status(
    session: AsyncSession,
    feedback_id: int,
    read_state: str | None = None,
    resolved_state: str | None = None,
) -> bool:
    """Update feedback status flags."""
    feedback = (
        await session.execute(select(Feedback).where(Feedback.id == feedback_id).limit(1))
    ).scalar_one_or_none()
    if not feedback:
        return False
    current_read, current_resolved = _feedback_status_flags(feedback.status)
    final_read = read_state if read_state in {"unread", "read"} else current_read
    final_resolved = resolved_state if resolved_state in {"unresolved", "resolved"} else current_resolved
    feedback.status = f"{final_read}_{final_resolved}"
    await session.flush()
    return True


async def add_feedback_reply(
    session: AsyncSession,
    feedback_id: int,
    message: str,
) -> FeedbackReply | None:
    """Persist admin reply text for feedback."""
    feedback = (
        await session.execute(select(Feedback).where(Feedback.id == feedback_id).limit(1))
    ).scalar_one_or_none()
    if not feedback:
        return None
    reply = FeedbackReply(feedback_id=feedback_id, message=(message or "").strip())
    session.add(reply)
    feedback.status = "read_unresolved"
    await session.flush()
    return reply


async def get_feedback_unread_count(session: AsyncSession) -> int:
    """Количество обращений со статусом unread_*."""
    q = (
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.status.ilike("unread_%"))
    )
    return int((await session.execute(q)).scalar() or 0)
