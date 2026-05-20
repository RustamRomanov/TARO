"""Simple async cache wrapper: Redis (if configured) with in-memory fallback."""

from datetime import datetime, timedelta, timezone
from typing import Any
import json
import logging
import asyncio
import secrets

from app.core.config import get_settings

logger = logging.getLogger(__name__)

try:
    from redis.asyncio import Redis  # type: ignore
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

_redis_client: Any = None
_memory_cache: dict[str, tuple[datetime, str]] = {}
_LOCK_NO_REDIS = "__no_redis__"


def _get_redis() -> Any | None:
    """Lazy Redis client creation."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = (get_settings().REDIS_URL or "").strip()
    if not url or Redis is None:
        return None
    try:
        _redis_client = Redis.from_url(url, decode_responses=True)
        return _redis_client
    except Exception:
        logger.exception("Failed to init Redis client; fallback to in-memory cache.")
        return None


async def get_json(key: str) -> Any | None:
    """Get JSON value by key."""
    redis = _get_redis()
    if redis is not None:
        try:
            value = await redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            logger.exception("Redis get failed for key=%s", key)
    now = datetime.now(timezone.utc)
    item = _memory_cache.get(key)
    if not item:
        return None
    expires_at, raw = item
    if expires_at <= now:
        _memory_cache.pop(key, None)
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def delete_json(key: str) -> None:
    """Удалить ключ (Redis + in-memory)."""
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.delete(key)
        except Exception:
            logger.exception("Redis delete failed for key=%s", key)
    _memory_cache.pop(key, None)


async def set_json(key: str, payload: Any, ttl_seconds: int) -> None:
    """Set JSON value by key with TTL."""
    raw = json.dumps(payload, ensure_ascii=False)
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.set(key, raw, ex=max(1, int(ttl_seconds)))
            return
        except Exception:
            logger.exception("Redis set failed for key=%s", key)
    # In-memory fallback: не работает при нескольких воркерах/репликах
    if key.startswith("tarot_share:"):
        logger.warning("tarot_share использует in-memory кэш. Для «Выбрать получателей» добавьте REDIS_URL.")
    _memory_cache[key] = (datetime.now(timezone.utc) + timedelta(seconds=max(1, int(ttl_seconds))), raw)


async def acquire_lock(
    key: str,
    *,
    ttl_seconds: int = 20,
    wait_timeout_seconds: float = 0.0,
    retry_delay_ms: int = 80,
) -> str | None:
    """
    Acquire distributed lock in Redis via SET key value NX EX ttl.
    Returns token when acquired, None when timed out.
    If Redis is not configured, returns sentinel token (best-effort no-op lock).
    """
    redis = _get_redis()
    if redis is None:
        return _LOCK_NO_REDIS

    token = secrets.token_hex(16)
    ttl = max(1, int(ttl_seconds))
    deadline = datetime.now(timezone.utc).timestamp() + max(0.0, float(wait_timeout_seconds))
    delay = max(10, int(retry_delay_ms)) / 1000.0

    while True:
        try:
            ok = await redis.set(key, token, ex=ttl, nx=True)
            if ok:
                return token
        except Exception:
            logger.exception("Redis acquire_lock failed for key=%s", key)
            return None
        if wait_timeout_seconds <= 0:
            return None
        if datetime.now(timezone.utc).timestamp() >= deadline:
            return None
        await asyncio.sleep(delay)


async def release_lock(key: str, token: str | None) -> None:
    """Release Redis lock only if token matches (safe unlock)."""
    if not token:
        return
    if token == _LOCK_NO_REDIS:
        return
    redis = _get_redis()
    if redis is None:
        return
    try:
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) "
            "else return 0 end"
        )
        await redis.eval(script, 1, key, token)
    except Exception:
        logger.exception("Redis release_lock failed for key=%s", key)
