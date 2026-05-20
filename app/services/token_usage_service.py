"""Сохранение учёта токенов в БД (фоново, без блокировки ответа)."""
import asyncio
import logging
from typing import Any, Optional

from app.core.security import sanitize_profile_id_for_db
from app.db.models.token_usage import TokenUsage
from app.db.session import async_session_factory
from app.services.token_calculator import calculate_cost, get_exchange_rate

logger = logging.getLogger(__name__)


async def save_token_usage_async(
    user_id: int,
    feature_type: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int = 0,
    cached_tokens: int = 0,
    request_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    error: bool = False,
    profile_id: Optional[int] = None,
    metadata_: Optional[dict[str, Any]] = None,
) -> None:
    """
    Сохранить запись об использовании токенов в БД (вызывать через asyncio.create_task).
    user_id обязателен (telegram_id). При error=True токены могут быть 0.
    """
    try:
        async with async_session_factory() as session:
            try:
                rate = await get_exchange_rate(session)
            except Exception as e:
                logger.warning("Token usage: get_exchange_rate failed, using default: %s", e)
                rate = 95.0
            total = total_tokens or (prompt_tokens + completion_tokens)
            # Некоторые провайдеры отдают только total_tokens без разбивки prompt/completion.
            # В этом случае считаем весь объём как prompt, чтобы не терять рублёвую оценку.
            pt = int(prompt_tokens or 0)
            ct = int(completion_tokens or 0)
            if total > 0 and pt == 0 and ct == 0:
                pt = int(total)

            if error:
                cost_usd, cost_rub = 0.0, 0.0
            else:
                cost_usd, cost_rub = calculate_cost(
                    provider,
                    model,
                    pt,
                    ct,
                    cached_tokens=int(cached_tokens or 0),
                    exchange_rate=rate,
                )
            profile_id_safe = sanitize_profile_id_for_db(profile_id)
            if profile_id_safe is not None and (profile_id_safe < 1 or profile_id_safe > 2147483647):
                profile_id_safe = None
            row = TokenUsage(
                user_id=user_id,
                profile_id=profile_id_safe,
                feature_type=feature_type,
                provider=provider,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=total,
                cached_tokens=cached_tokens,
                cost_usd=cost_usd,
                cost_rub=cost_rub,
                request_id=request_id,
                latency_ms=latency_ms,
                error=error,
                metadata_=metadata_,
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.exception("Token usage save failed: %s", e)


def schedule_save_token_usage(
    user_id: Optional[int],
    feature_type: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int = 0,
    cached_tokens: int = 0,
    request_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    error: bool = False,
    profile_id: Optional[int] = None,
    metadata_: Optional[dict[str, Any]] = None,
) -> None:
    """Запустить сохранение в фоне. Если user_id нет - не сохраняем (FK)."""
    if user_id is None:
        return
    asyncio.create_task(
        save_token_usage_async(
            user_id=user_id,
            feature_type=feature_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            request_id=request_id,
            latency_ms=latency_ms,
            error=error,
            profile_id=profile_id,
            metadata_=metadata_,
        )
    )
