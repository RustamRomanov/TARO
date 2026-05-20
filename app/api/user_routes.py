"""User auth and trial (TARO: no profiles / natal data)."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_telegram_user_from_init_data
from app.db.models import User
from app.db.session import get_db
from app.services.limits import (
    TRIAL_DAYS,
    _ensure_user,
    _reset_daily_if_needed,
    build_limits_for_auth,
    sync_expired_subscription_status,
)
from app.services.subscription_expiry_notifications import notify_subscription_expiry_on_auth

router = APIRouter(prefix="/user", tags=["user"])
logger = logging.getLogger(__name__)


class AuthRequest(BaseModel):
    init_data: str = ""


class AuthResponse(BaseModel):
    user: dict
    status: str
    limits: dict


class ActivateTrialRequest(BaseModel):
    init_data: str = ""


class ActivateTrialResponse(BaseModel):
    ok: bool
    status: str
    trial_ends_at: str | None
    message: str


@router.post("/auth", response_model=AuthResponse)
async def auth(
    payload: AuthRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Validate initData, get or create user, return user + status + limits."""
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")

    telegram_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")

    try:
        user = await _ensure_user(
            db,
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
        )
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=409, detail="User conflict.")
    user = await _reset_daily_if_needed(db, user)
    await sync_expired_subscription_status(db, user)
    await notify_subscription_expiry_on_auth(db, user)
    user.last_seen_at = datetime.now(timezone.utc)
    await db.flush()

    return AuthResponse(
        user={
            "telegram_id": user.telegram_id,
            "username": user.username,
            "full_name": user.full_name,
        },
        status=user.status,
        limits=await build_limits_for_auth(db, user),
    )


@router.post("/activate-trial", response_model=ActivateTrialResponse)
async def activate_trial(
    payload: ActivateTrialRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivateTrialResponse:
    """Activate 3-day trial if not yet used."""
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    telegram_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")

    user = await _ensure_user(db, telegram_id, username=username, full_name=full_name)

    if user.is_trial_used:
        return ActivateTrialResponse(
            ok=False,
            status=user.status,
            trial_ends_at=user.trial_ends_at.isoformat() if user.trial_ends_at else None,
            message="Пробный период уже был использован.",
        )

    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
    user.status = "trial"
    user.is_trial_used = True
    user.trial_ends_at = trial_ends_at
    await db.flush()

    return ActivateTrialResponse(
        ok=True,
        status="trial",
        trial_ends_at=trial_ends_at.isoformat(),
        message="Пробный период 3 дня активирован.",
    )
