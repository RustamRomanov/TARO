"""Security: JWT, Telegram initData validation, etc."""
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl, unquote

from app.core.config import get_settings


def validate_telegram_init_data(init_data: str) -> dict[str, Any] | None:
    """Validate Telegram Mini App initData and return parsed payload (with user) or None."""
    if not init_data or not init_data.strip():
        return None
    token = get_settings().TELEGRAM_BOT_TOKEN
    if not token:
        return None
    try:
        parsed = dict(parse_qsl(unquote(init_data), keep_blank_values=True))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(
            b"WebAppData",
            token.encode(),
            hashlib.sha256,
        ).digest()
        computed = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, hash_val):
            return None
        auth_date_raw = str(parsed.get("auth_date") or "").strip()
        if not auth_date_raw:
            return None
        auth_date = int(auth_date_raw)
        now_ts = int(time.time())
        max_age = max(60, int(get_settings().TELEGRAM_INIT_DATA_MAX_AGE_SECONDS or 900))
        skew = max(0, int(get_settings().TELEGRAM_INIT_DATA_CLOCK_SKEW_SECONDS or 60))
        if auth_date > now_ts + skew:
            return None
        if now_ts - auth_date > max_age:
            return None
        return parsed
    except Exception:
        return None


def sanitize_profile_id_for_db(profile_id: int | None) -> int | None:
    """Приводит profile_id к int32: клиент может передать Telegram user id - не передаём в БД (Profile.id = Integer)."""
    if profile_id is None:
        return None
    if profile_id < -2147483648 or profile_id > 2147483647:
        return None
    return profile_id


def get_telegram_user_id_from_init_data(init_data: str) -> int | None:
    """Validate init_data and return Telegram user id or None."""
    settings = get_settings()
    token = (init_data or "").strip()
    if settings.DEBUG and settings.ALLOW_DEV_AUTH and token in ("", "dev_local"):
        return int(settings.DEV_TELEGRAM_USER_ID or 999000001)
    payload = validate_telegram_init_data(init_data)
    if not payload or "user" not in payload:
        return None
    try:
        user = json.loads(payload["user"])
        return int(user.get("id"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def get_telegram_user_from_init_data(init_data: str) -> dict | None:
    """Validate init_data and return Telegram user dict (id, username, first_name, last_name) or None."""
    settings = get_settings()
    token = (init_data or "").strip()
    if settings.DEBUG and settings.ALLOW_DEV_AUTH and token in ("", "dev_local"):
        dev_id = int(settings.DEV_TELEGRAM_USER_ID or 999000001)
        return {
            "id": dev_id,
            "username": "dev_user",
            "first_name": "Dev",
            "last_name": "User",
        }
    payload = validate_telegram_init_data(init_data)
    if not payload or "user" not in payload:
        return None
    try:
        user = json.loads(payload["user"])
        return {
            "id": int(user.get("id")),
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
        }
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None
