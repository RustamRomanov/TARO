"""User auth, trial activation, limits."""
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_telegram_user_from_init_data, get_telegram_user_id_from_init_data
from app.core.uploads_dir import get_uploads_root
from app.db.models import Profile, User
from app.db.session import get_db
from app.services.birth_place import normalize_stored_birth_place
from app.services.gender import infer_gender_by_ai, infer_gender_from_name
from app.services.cache import get_json as cache_get_json, set_json as cache_set_json
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

_AVATAR_MAX_SIZE = 2 * 1024 * 1024
_AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def _profile_sync_idempotency_key(telegram_id: int, payload: "ProfileSyncRequest") -> str:
    raw = json.dumps(
        {
            "u": int(telegram_id),
            "name": (payload.name or "").strip(),
            "birth_date": (payload.birth_date or "").strip(),
            "birth_time": (payload.birth_time or "").strip(),
            "birth_city": (payload.birth_city or "").strip(),
            "birth_lat": round(float(payload.birth_lat), 6) if payload.birth_lat is not None else None,
            "birth_lon": round(float(payload.birth_lon), 6) if payload.birth_lon is not None else None,
            "gender": (payload.gender or "").strip(),
            "relationship_status": (payload.relationship_status or "").strip(),
            "occupation": (payload.occupation or "").strip(),
            "interests": payload.interests or [],
            "avatar_url": (payload.avatar_url or "").strip(),
            "avatar_remove": bool(payload.avatar_remove),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"profile_sync_idem:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _avatar_extension(content_type: str, filename: str) -> str:
    if content_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    lowered = (filename or "").lower()
    if lowered.endswith((".jpg", ".jpeg")):
        return ".jpg"
    if lowered.endswith(".png"):
        return ".png"
    if lowered.endswith(".webp"):
        return ".webp"
    return ".jpg"


def _normalize_relationship_status(value: str) -> str | None:
    raw = (value or "").strip().lower()
    allowed = {"single", "in_relationship", "married"}
    return raw if raw in allowed else None


def _normalize_occupation(value: str) -> str | None:
    raw = (value or "").strip().lower()
    allowed = {"employed", "business", "student", "homemaker", "retired", "other"}
    return raw if raw in allowed else None


def _normalize_interests(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    clean = [str(v).strip() for v in values if str(v).strip()]
    return clean[:20] or None


def _parse_birth_date(value: str) -> date | None:
    """Принимает дату в форматах YYYY-MM-DD, DD.MM.YYYY, DD MMM YYYY."""
    if not (value or "").strip():
        return None
    s = value.strip()
    normalized = s.replace(",", " ").replace("г.", " ").replace("г", " ").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    # e.g. "15 янв 2016", "15 jan 2016"
    m = re.match(r"^\s*(\d{1,2})\s+([a-zA-Zа-яА-ЯёЁ]{3,})\.?\s+(\d{4})\s*$", normalized)
    if m:
        day = int(m.group(1))
        month_raw = m.group(2).strip().lower()
        year = int(m.group(3))
        month_map = {
            "янв": 1, "январ": 1, "jan": 1,
            "фев": 2, "февр": 2, "feb": 2,
            "мар": 3, "март": 3, "mar": 3,
            "апр": 4, "апрел": 4, "apr": 4,
            "май": 5, "мая": 5, "may": 5,
            "июн": 6, "июнь": 6, "jun": 6,
            "июл": 7, "июль": 7, "jul": 7,
            "авг": 8, "август": 8, "aug": 8,
            "сен": 9, "сент": 9, "sep": 9,
            "окт": 10, "октя": 10, "oct": 10,
            "ноя": 11, "нояб": 11, "nov": 11,
            "дек": 12, "дека": 12, "dec": 12,
        }
        month = month_map.get(month_raw[:5], month_map.get(month_raw[:3]))
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


class AuthRequest(BaseModel):
    init_data: str = ""
    profile_name: str = ""
    profile_birth_date: str = ""
    profile_birth_time: str = ""
    profile_birth_city: str = ""
    profile_gender: str = ""


class AuthResponse(BaseModel):
    user: dict
    status: str
    limits: dict
    profiles_count: int


class ActivateTrialRequest(BaseModel):
    init_data: str = ""


class ActivateTrialResponse(BaseModel):
    ok: bool
    status: str
    trial_ends_at: str | None
    message: str


class ProfileCreateRequest(BaseModel):
    init_data: str = ""
    name: str = ""
    birth_date: str = ""
    birth_time: str = ""
    birth_city: str = ""
    birth_lat: float | None = None
    birth_lon: float | None = None
    gender: str = ""
    relationship_status: str = ""
    occupation: str = ""
    interests: list[str] | None = None
    is_primary: bool = False  # kept for backward compatibility; ignored in single-profile mode


class ProfileCreateResponse(BaseModel):
    id: int
    message: str


class ProfileSyncRequest(BaseModel):
    init_data: str = ""
    name: str = ""
    birth_date: str = ""
    birth_time: str = ""
    birth_city: str = ""
    birth_lat: float | None = None
    birth_lon: float | None = None
    gender: str = ""
    relationship_status: str = ""
    occupation: str = ""
    interests: list[str] | None = None
    avatar_url: str = ""
    avatar_remove: bool = False


class ProfileSyncResponse(BaseModel):
    ok: bool
    message: str


class ProfilePrimaryRequest(BaseModel):
    init_data: str = ""


class ProfilePrimaryResponse(BaseModel):
    id: int | None
    name: str | None
    birth_date: str | None
    birth_time: str | None
    birth_city: str | None
    birth_lat: float | None = None
    birth_lon: float | None = None
    gender: str | None
    relationship_status: str | None
    occupation: str | None
    interests: list[str] | None
    avatar_url: str | None


async def _upsert_profile_from_auth(
    db: AsyncSession,
    telegram_id: int,
    name: str = "",
    birth_date: str = "",
    birth_time: str = "12:00",
    birth_city: str = "",
    gender: str = "",
) -> None:
    """Создать/обновить профиль из данных auth (профиль из localStorage)."""
    birth_parsed = _parse_birth_date(birth_date)
    explicit_gender = _normalize_gender(gender)
    inferred_gender = explicit_gender or (infer_gender_from_name(name) if name else None)
    if inferred_gender is None and name:
        try:
            from app.services.ai_client import AIServiceClient
            inferred_gender = await infer_gender_by_ai(AIServiceClient(), name)
        except Exception:
            pass
    profile = await _canonicalize_profile_for_user(db, telegram_id)
    if profile:
        if name:
            profile.name = name
        if birth_parsed:
            profile.birth_date = birth_parsed
        if birth_time:
            profile.birth_time = birth_time
        if birth_city:
            resolved = normalize_stored_birth_place(birth_city, None, None)
            if resolved[0] is not None:
                profile.birth_city = resolved[0]
                profile.birth_lat = resolved[1]
                profile.birth_lon = resolved[2]
            else:
                profile.birth_city = birth_city
                profile.birth_lat = None
                profile.birth_lon = None
        if inferred_gender:
            profile.gender = inferred_gender
    else:
        bcity: str | None = None
        blat: float | None = None
        blon: float | None = None
        if birth_city:
            resolved = normalize_stored_birth_place(birth_city, None, None)
            if resolved[0] is not None:
                bcity, blat, blon = resolved
            else:
                bcity = birth_city.strip()
        profile = Profile(
            user_id=telegram_id,
            name=name or None,
            birth_date=birth_parsed,
            birth_time=birth_time or None,
            birth_city=bcity,
            birth_lat=blat,
            birth_lon=blon,
            gender=inferred_gender,
            is_primary=True,
        )
        db.add(profile)
    await db.flush()


def _profile_has_value(raw: str | None) -> bool:
    return bool((raw or "").strip())


def _profile_priority_key(profile: Profile) -> tuple[int, ...]:
    return (
        1 if profile.birth_date else 0,
        1 if _profile_has_value(profile.birth_city) else 0,
        1 if _profile_has_value(profile.name) else 0,
        1 if _profile_has_value(profile.gender) else 0,
        1 if _profile_has_value(profile.relationship_status) else 0,
        1 if _profile_has_value(profile.occupation) else 0,
        1 if bool(profile.interests) else 0,
        1 if _profile_has_value(profile.avatar_url) else 0,
        1 if bool(getattr(profile, "is_primary", False)) else 0,
        int(profile.id or 0),
    )


def _merge_missing_profile_fields(target: Profile, source: Profile) -> None:
    if not _profile_has_value(target.name) and _profile_has_value(source.name):
        target.name = source.name
    if target.birth_date is None and source.birth_date is not None:
        target.birth_date = source.birth_date
    if not _profile_has_value(target.birth_time) and _profile_has_value(source.birth_time):
        target.birth_time = source.birth_time
    if not _profile_has_value(target.birth_city) and _profile_has_value(source.birth_city):
        target.birth_city = source.birth_city
    if (target.birth_lat is None or target.birth_lon is None) and source.birth_lat is not None and source.birth_lon is not None:
        target.birth_lat = source.birth_lat
        target.birth_lon = source.birth_lon
    if not _profile_has_value(target.gender) and _profile_has_value(source.gender):
        target.gender = source.gender
    if not _profile_has_value(target.relationship_status) and _profile_has_value(source.relationship_status):
        target.relationship_status = source.relationship_status
    if not _profile_has_value(target.occupation) and _profile_has_value(source.occupation):
        target.occupation = source.occupation
    if not target.interests and source.interests:
        target.interests = source.interests
    if not _profile_has_value(target.avatar_url) and _profile_has_value(source.avatar_url):
        target.avatar_url = source.avatar_url


async def _canonicalize_profile_for_user(db: AsyncSession, telegram_id: int) -> Profile | None:
    """
    Choose one canonical profile for user and merge missing fields from duplicates.
    Keeps data automatic for old duplicated rows without manual fixes.
    """
    result = await db.execute(
        select(Profile).where(Profile.user_id == telegram_id).order_by(Profile.id.asc())
    )
    profiles = result.scalars().all()
    if not profiles:
        return None

    canonical = max(profiles, key=_profile_priority_key)
    for p in profiles:
        if p.id == canonical.id:
            continue
        _merge_missing_profile_fields(canonical, p)
        if p.is_primary:
            canonical.is_primary = True
        p.is_primary = False
    canonical.is_primary = True
    await db.flush()
    return canonical


def _normalize_gender(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if raw in {"m", "male", "man", "м"}:
        return "m"
    if raw in {"f", "female", "woman", "ж"}:
        return "f"
    return None


@router.post("/auth", response_model=AuthResponse)
async def auth(
    payload: AuthRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """
    Validate initData, get or create user, return user + status + limits + profiles_count.
    """
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

    if (
        (payload.profile_name or "").strip()
        or (payload.profile_birth_date or "").strip()
        or (payload.profile_birth_city or "").strip()
        or (payload.profile_gender or "").strip()
    ):
        await _upsert_profile_from_auth(
            db,
            telegram_id,
            name=(payload.profile_name or "").strip(),
            birth_date=(payload.profile_birth_date or "").strip(),
            birth_time=(payload.profile_birth_time or "").strip() or "12:00",
            birth_city=(payload.profile_birth_city or "").strip(),
            gender=(payload.profile_gender or "").strip(),
        )

    canonical = await _canonicalize_profile_for_user(db, telegram_id)
    profiles_count = 1 if canonical else 0

    return AuthResponse(
        user={
            "telegram_id": user.telegram_id,
            "username": user.username,
            "full_name": user.full_name,
        },
        status=user.status,
        limits=await build_limits_for_auth(db, user),
        profiles_count=profiles_count,
    )


@router.post("/activate-trial", response_model=ActivateTrialResponse)
async def activate_trial(
    payload: ActivateTrialRequest,
    db: AsyncSession = Depends(get_db),
) -> ActivateTrialResponse:
    """
    Activate 3-day trial if not yet used. Sets status=trial, is_trial_used=True, trial_ends_at=now+3 days.
    """
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


@router.post("/profiles", response_model=ProfileCreateResponse)
async def create_profile(
    payload: ProfileCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ProfileCreateResponse:
    """Create or update the single user profile."""
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    telegram_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")

    await _ensure_user(db, telegram_id, username=username, full_name=full_name)

    birth_date_parsed = _parse_birth_date(payload.birth_date)
    explicit_gender = _normalize_gender(payload.gender)
    relationship_status = _normalize_relationship_status(payload.relationship_status)
    occupation = _normalize_occupation(payload.occupation)
    interests = _normalize_interests(payload.interests)
    inferred_gender = explicit_gender or (infer_gender_from_name(payload.name) if payload.name else None)
    if inferred_gender is None and (payload.name or "").strip():
        try:
            from app.services.ai_client import AIServiceClient
            inferred_gender = await infer_gender_by_ai(AIServiceClient(), payload.name)
        except Exception:
            pass
    profile = await _canonicalize_profile_for_user(db, telegram_id)
    place_city: str | None = None
    place_lat: float | None = None
    place_lon: float | None = None
    if (payload.birth_city or "").strip():
        place_city, place_lat, place_lon = normalize_stored_birth_place(
            payload.birth_city, payload.birth_lat, payload.birth_lon
        )

    if profile:
        incoming_name = (payload.name or "").strip()
        incoming_city = (payload.birth_city or "").strip()
        incoming_time = (payload.birth_time or "").strip()
        if incoming_name:
            profile.name = incoming_name
        if birth_date_parsed:
            profile.birth_date = birth_date_parsed
        if incoming_time:
            profile.birth_time = incoming_time
        if incoming_city:
            profile.birth_city = place_city
            profile.birth_lat = place_lat
            profile.birth_lon = place_lon
        if inferred_gender:
            profile.gender = inferred_gender
        if relationship_status:
            profile.relationship_status = relationship_status
        if occupation:
            profile.occupation = occupation
        if interests is not None:
            profile.interests = interests
        await db.flush()
        return ProfileCreateResponse(id=profile.id, message="Профиль обновлён.")

    profile = Profile(
        user_id=telegram_id,
        name=(payload.name or "").strip() or None,
        birth_date=birth_date_parsed,
        birth_time=(payload.birth_time or "").strip() or None,
        birth_city=place_city,
        birth_lat=place_lat,
        birth_lon=place_lon,
        is_primary=True,
        gender=inferred_gender,
        relationship_status=relationship_status,
        occupation=occupation,
        interests=interests,
    )
    db.add(profile)
    await db.flush()
    return ProfileCreateResponse(id=profile.id, message="Профиль создан.")


@router.post("/profile/sync", response_model=ProfileSyncResponse)
async def sync_primary_profile(
    payload: ProfileSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> ProfileSyncResponse:
    """
    Синхронизирует первичный профиль из приложения: создаёт или обновляет запись с датой рождения и именем.
    Нужен для отображения возраста в админке и для расчётов по профилю.
    """
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    telegram_id = tg_user["id"]
    idem_key = _profile_sync_idempotency_key(telegram_id, payload)
    cached = await cache_get_json(idem_key)
    if isinstance(cached, dict) and bool(cached.get("ok")):
        return ProfileSyncResponse(ok=True, message=str(cached.get("message") or "Профиль обновлён."))
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")

    await _ensure_user(db, telegram_id, username=username, full_name=full_name)

    profile = await _canonicalize_profile_for_user(db, telegram_id)

    birth_date_parsed = _parse_birth_date(payload.birth_date)
    logger.info(
        "profile_sync_in user_id=%s username=%s raw_name=%s raw_birth_date=%s raw_birth_city=%s raw_gender=%s parsed_birth_date=%s",
        telegram_id,
        username,
        (payload.name or "").strip(),
        (payload.birth_date or "").strip(),
        (payload.birth_city or "").strip(),
        (payload.gender or "").strip(),
        birth_date_parsed.isoformat() if birth_date_parsed else "",
    )
    explicit_gender = _normalize_gender(payload.gender)
    relationship_status = _normalize_relationship_status(payload.relationship_status)
    occupation = _normalize_occupation(payload.occupation)
    interests = _normalize_interests(payload.interests)
    inferred_gender = explicit_gender or (infer_gender_from_name(payload.name) if payload.name else None)
    if inferred_gender is None and (payload.name or "").strip():
        try:
            from app.services.ai_client import AIServiceClient
            inferred_gender = await infer_gender_by_ai(AIServiceClient(), payload.name)
        except Exception:
            pass

    incoming_avatar = (payload.avatar_url or "").strip()
    if incoming_avatar and not incoming_avatar.startswith(("http://", "https://", "/")):
        incoming_avatar = ""

    place_city: str | None = None
    place_lat: float | None = None
    place_lon: float | None = None
    if (payload.birth_city or "").strip():
        place_city, place_lat, place_lon = normalize_stored_birth_place(
            payload.birth_city, payload.birth_lat, payload.birth_lon
        )

    if profile:
        # Do not erase existing profile data with empty sync payloads.
        # Frontend may occasionally send partial data during hydration.
        incoming_name = (payload.name or "").strip()
        incoming_city = (payload.birth_city or "").strip()
        incoming_time = (payload.birth_time or "").strip()
        if incoming_name:
            profile.name = incoming_name
        if birth_date_parsed:
            profile.birth_date = birth_date_parsed
        if incoming_time:
            profile.birth_time = incoming_time
        if incoming_city:
            profile.birth_city = place_city
            profile.birth_lat = place_lat
            profile.birth_lon = place_lon
        if inferred_gender:
            profile.gender = inferred_gender
        if relationship_status:
            profile.relationship_status = relationship_status
        if occupation:
            profile.occupation = occupation
        if interests is not None:
            profile.interests = interests
        if payload.avatar_remove:
            await db.execute(
                update(Profile)
                .where(Profile.user_id == telegram_id)
                .values(avatar_url=None)
            )
            profile.avatar_url = None
        elif incoming_avatar:
            profile.avatar_url = incoming_avatar
        await db.flush()
        logger.info(
            "profile_sync_out user_id=%s profile_id=%s name=%s birth_date=%s birth_city=%s gender=%s",
            telegram_id,
            profile.id,
            profile.name or "",
            profile.birth_date.isoformat() if profile.birth_date else "",
            profile.birth_city or "",
            profile.gender or "",
        )
        response = ProfileSyncResponse(ok=True, message="Профиль обновлён.")
        await cache_set_json(idem_key, {"ok": True, "message": response.message}, ttl_seconds=15)
        return response
    else:
        profile = Profile(
            user_id=telegram_id,
            name=payload.name or None,
            birth_date=birth_date_parsed,
            birth_time=payload.birth_time or None,
            birth_city=place_city,
            birth_lat=place_lat,
            birth_lon=place_lon,
            avatar_url=incoming_avatar or None,
            is_primary=True,
            gender=inferred_gender,
            relationship_status=relationship_status,
            occupation=occupation,
            interests=interests,
        )
        db.add(profile)
        await db.flush()
        logger.info(
            "profile_sync_out user_id=%s profile_id=%s name=%s birth_date=%s birth_city=%s gender=%s",
            telegram_id,
            profile.id,
            profile.name or "",
            profile.birth_date.isoformat() if profile.birth_date else "",
            profile.birth_city or "",
            profile.gender or "",
        )
        response = ProfileSyncResponse(ok=True, message="Профиль создан.")
        await cache_set_json(idem_key, {"ok": True, "message": response.message}, ttl_seconds=15)
        return response


@router.post("/profile/primary", response_model=ProfilePrimaryResponse)
async def get_primary_profile(
    payload: ProfilePrimaryRequest,
    db: AsyncSession = Depends(get_db),
) -> ProfilePrimaryResponse:
    """Вернуть основной профиль пользователя (для подстановки данных при пустом localStorage)."""
    telegram_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Необходима авторизация через Telegram.")
    profile = await _canonicalize_profile_for_user(db, telegram_id)
    if not profile:
        return ProfilePrimaryResponse(
            id=None,
            name=None,
            birth_date=None,
            birth_time=None,
            birth_city=None,
            birth_lat=None,
            birth_lon=None,
            gender=None,
            relationship_status=None,
            occupation=None,
            interests=None,
            avatar_url=None,
        )
    return ProfilePrimaryResponse(
        id=profile.id,
        name=profile.name,
        birth_date=profile.birth_date.isoformat() if profile.birth_date else None,
        birth_time=profile.birth_time,
        birth_city=profile.birth_city,
        birth_lat=profile.birth_lat,
        birth_lon=profile.birth_lon,
        gender=profile.gender,
        relationship_status=profile.relationship_status,
        occupation=profile.occupation,
        interests=profile.interests,
        avatar_url=profile.avatar_url,
    )


class AvatarUploadResponse(BaseModel):
    avatar_url: str


class AvatarRemoveResponse(BaseModel):
    ok: bool


@router.post("/profile/avatar", response_model=AvatarUploadResponse)
async def upload_profile_avatar(
    init_data: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> AvatarUploadResponse:
    """Загрузка аватара. Сохраняет в static/uploads/avatars/{telegram_id}/. Возвращает URL пути."""
    tg_user = get_telegram_user_from_init_data(init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    telegram_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")
    await _ensure_user(db, telegram_id, username=username, full_name=full_name)

    content_type = (file.content_type or "").lower()
    if content_type not in _AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Допустимы только JPG/PNG/WEBP.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(payload) > _AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Размер не более 2 МБ.")

    ext = _avatar_extension(content_type, file.filename or "")
    upload_dir = get_uploads_root() / "avatars" / str(telegram_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4().hex}{ext}"
    file_path = upload_dir / file_name
    file_path.write_bytes(payload)

    path = f"/uploads/avatars/{telegram_id}/{file_name}"
    profile = await _canonicalize_profile_for_user(db, telegram_id)
    if profile:
        profile.avatar_url = path
    else:
        profile = Profile(
            user_id=telegram_id,
            avatar_url=path,
            is_primary=True,
        )
        db.add(profile)
    await db.flush()
    return AvatarUploadResponse(avatar_url=path)


@router.post("/profile/avatar/remove", response_model=AvatarRemoveResponse)
async def remove_profile_avatar(
    payload: ProfilePrimaryRequest,
    db: AsyncSession = Depends(get_db),
) -> AvatarRemoveResponse:
    """Удаление аватара пользователя."""
    tg_user = get_telegram_user_from_init_data(payload.init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    telegram_id = tg_user["id"]
    parts = [tg_user.get("first_name"), tg_user.get("last_name")]
    full_name = (" ".join(filter(None, parts)).strip() or None)
    username = tg_user.get("username")
    await _ensure_user(db, telegram_id, username=username, full_name=full_name)
    await db.execute(
        update(Profile)
        .where(Profile.user_id == telegram_id)
        .values(avatar_url=None)
    )
    return AvatarRemoveResponse(ok=True)
