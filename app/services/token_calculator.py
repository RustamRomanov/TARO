"""Расчёт стоимости AI-запросов по токенам и авто-курс USD/RUB."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_setting import AdminSetting
from app.db.models.admin_setting import ADMIN_SETTING_USD_RUB as _KEY_RATE

# Цены в USD за 1M токенов (input, output, cached_input)
# https://openai.com/api/pricing
PRICING_OPENAI = {
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "gpt-4": {"input": 30.00, "output": 60.00, "cached": 15.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "cached": 5.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50, "cached": 0.25},
}

# DeepSeek: USD per 1M tokens
# https://api-docs.deepseek.com/quick_start/pricing/
PRICING_DEEPSEEK = {
    "deepseek-chat": {"input": 0.28, "output": 0.42, "cached": 0.028},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19, "cached": 0.14},
}

# VseGPT.ru: рубли за 1000 токенов (вход+выход вместе)
PRICING_VSEGPT_RUB_PER_1K = {
    "default": 2.0,
}


def _get_openai_pricing(model: str) -> Tuple[float, float, float]:
    base = model.split("-")[0]
    for key in ("gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"):
        if key in model or model.startswith(key.split("-")[0]):
            p = PRICING_OPENAI.get(key, PRICING_OPENAI["gpt-4o-mini"])
            return p["input"], p["output"], p["cached"]
    return PRICING_OPENAI["gpt-4o-mini"]["input"], PRICING_OPENAI["gpt-4o-mini"]["output"], PRICING_OPENAI["gpt-4o-mini"]["cached"]


def _get_deepseek_pricing(model: str) -> Tuple[float, float, float]:
    p = PRICING_DEEPSEEK.get(model, PRICING_DEEPSEEK["deepseek-chat"])
    return p["input"], p["output"], p["cached"]


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    exchange_rate: float = 95.0,
) -> Tuple[float, float]:
    """
    Возвращает (cost_usd, cost_rub).
    provider: openai | deepseek | vsegpt
    """
    if provider == "openai":
        inp, out, cached = _get_openai_pricing(model)
        input_billable = max(0, prompt_tokens - cached_tokens)
        cost_usd = (input_billable * inp / 1_000_000) + (cached_tokens * cached / 1_000_000) + (completion_tokens * out / 1_000_000)
        return round(cost_usd, 6), round(cost_usd * exchange_rate, 2)
    if provider == "deepseek":
        inp, out, cached = _get_deepseek_pricing(model)
        input_billable = max(0, prompt_tokens - cached_tokens)
        cost_usd = (input_billable * inp / 1_000_000) + (cached_tokens * cached / 1_000_000) + (completion_tokens * out / 1_000_000)
        return round(cost_usd, 6), round(cost_usd * exchange_rate, 2)
    if provider == "vsegpt":
        price_per_1k = PRICING_VSEGPT_RUB_PER_1K.get(model, PRICING_VSEGPT_RUB_PER_1K["default"])
        total_tokens = prompt_tokens + completion_tokens
        cost_rub = total_tokens * price_per_1k / 1000
        cost_usd = cost_rub / exchange_rate if exchange_rate else 0
        return round(cost_usd, 6), round(cost_rub, 2)
    return 0.0, 0.0


ADMIN_SETTING_USD_RUB = "usd_rub_rate"
DEFAULT_EXCHANGE_RATE = 95.0
AUTO_RATE_REFRESH_HOURS = 6
CBR_DAILY_XML_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


def _parse_rate(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.01, float(str(value).replace(",", ".").strip()))
    except (ValueError, TypeError):
        return None


def _fetch_cbr_usd_rate_sync() -> float | None:
    try:
        with urlopen(CBR_DAILY_XML_URL, timeout=8) as resp:  # nosec - trusted CBR endpoint
            body = resp.read()
        root = ET.fromstring(body)
        for valute in root.findall("Valute"):
            code = valute.findtext("CharCode")
            if (code or "").strip().upper() != "USD":
                continue
            nominal_text = valute.findtext("Nominal")
            value_text = valute.findtext("Value")
            nominal = int((nominal_text or "1").strip())
            value = _parse_rate(value_text)
            if value is None or nominal <= 0:
                return None
            return round(value / nominal, 4)
    except Exception:
        return None
    return None


async def _fetch_cbr_usd_rate() -> float | None:
    return await asyncio.to_thread(_fetch_cbr_usd_rate_sync)


async def get_exchange_rate(session: AsyncSession) -> float:
    """Курс USD/RUB из admin_settings, автоматически обновляется из ЦБ РФ."""
    r = await session.execute(
        select(AdminSetting.value, AdminSetting.updated_at)
        .where(AdminSetting.key == _KEY_RATE)
        .limit(1)
    )
    row = r.one_or_none()
    current_rate = _parse_rate(row[0] if row else None) or DEFAULT_EXCHANGE_RATE
    updated_at = row[1] if row else None
    if updated_at and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    stale = (
        row is None
        or updated_at is None
        or (datetime.now(timezone.utc) - updated_at) >= timedelta(hours=AUTO_RATE_REFRESH_HOURS)
    )
    if stale:
        auto_rate = await _fetch_cbr_usd_rate()
        if auto_rate is not None:
            await update_exchange_rate(session, auto_rate)
            return auto_rate
    return current_rate


async def update_exchange_rate(session: AsyncSession, rate: float | None = None) -> float:
    """Сохранить курс в admin_settings. Если rate=None - подтянуть из ЦБ РФ."""
    from sqlalchemy import update
    if rate is None:
        fetched = await _fetch_cbr_usd_rate()
        if fetched is None:
            return DEFAULT_EXCHANGE_RATE
        rate = fetched
    safe_rate = max(0.01, float(rate))
    val = str(round(safe_rate, 4))
    r = await session.execute(select(AdminSetting.key).where(AdminSetting.key == _KEY_RATE).limit(1))
    exists = r.scalar() is not None
    if exists:
        await session.execute(
            update(AdminSetting)
            .where(AdminSetting.key == _KEY_RATE)
            .values(value=val, updated_at=func.now())
        )
    else:
        session.add(AdminSetting(key=_KEY_RATE, value=val))
    await session.flush()
    return safe_rate
