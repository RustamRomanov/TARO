"""Роуты админ-панели: логин, дашборд, пользователи, статистика, финансы."""
import asyncio
import hmac
import logging
from html import escape
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Form
import csv
import io

from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import FSInputFile

from app.bot.main import get_bot
from app.core.config import get_settings
from app.core.template_response import template_page
from app.core.templates_path import resolve_templates_directory
from app.core.uploads_dir import get_uploads_root, uploads_public_path_to_fs
from app.db.models import FeedbackAttachment
from app.db.session import get_db
from app.admin_panel import services
from app.services.user_bot_chat_status import record_bot_unreachable_from_telegram_error

_templates_path = resolve_templates_directory()
templates = Jinja2Templates(directory=str(_templates_path))
logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["admin"])
_MAX_SUPPORT_IMAGE_SIZE = 2 * 1024 * 1024
_MAX_ADMIN_USER_DM_LEN = 4096
_ALLOWED_SUPPORT_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_SESSION_ADMIN_KEY = "admin_logged_in"
_ADMIN_LOGIN_FALLBACK_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Astrov Admin Login</title>
  <style>
    body { font-family: Arial, sans-serif; background:#0b0b1e; color:#fff; margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; }
    .card { width:100%; max-width:380px; border:1px solid rgba(251,191,36,.35); border-radius:12px; padding:20px; background:rgba(0,0,0,.35); }
    h1 { margin:0 0 14px 0; color:#fbbf24; font-size:20px; }
    label { display:block; margin:10px 0 6px; color:rgba(255,255,255,.8); font-size:13px; }
    input { width:100%; box-sizing:border-box; border-radius:8px; border:1px solid rgba(251,191,36,.3); background:#14142b; color:#fff; padding:10px; }
    button { width:100%; margin-top:14px; border-radius:8px; border:1px solid rgba(251,191,36,.5); background:rgba(251,191,36,.18); color:#fbbf24; padding:10px; cursor:pointer; }
    .err { margin-top:10px; color:#fda4af; font-size:13px; }
  </style>
</head>
<body>
  <form class="card" method="post" action="/admin/login">
    <h1>Astrov Admin</h1>
    <label for="username">Логин</label>
    <input id="username" name="username" type="text" autocomplete="off">
    <label for="password">Пароль</label>
    <input id="password" name="password" type="password" autocomplete="off">
    <button type="submit">Войти</button>
    {error_html}
  </form>
</body>
</html>
"""


def _admin_authenticated(request: Request) -> bool:
    """Проверка, что в сессии есть успешный логин."""
    return bool(request.session.get(_SESSION_ADMIN_KEY))


def _check_credentials(username: str, password: str) -> bool:
    """Проверка логина и пароля (constant-time)."""
    settings = get_settings()
    expected_user = (settings.ADMIN_USERNAME or "").strip()
    expected_pass = (settings.ADMIN_PASSWORD or "").strip()
    if not expected_user or not expected_pass:
        return False
    return hmac.compare_digest(username.strip(), expected_user) and hmac.compare_digest(
        password, expected_pass
    )


async def require_admin(request: Request):
    """Если не авторизован, редирект на логин. Иначе None."""
    if _admin_authenticated(request):
        return None
    return RedirectResponse(url="/admin/login", status_code=302)


async def _safe_admin_call(call_name: str, coro, fallback):
    """Run admin data call with retries, then fallback."""
    attempts = 3
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro() if callable(coro) else await coro
        except Exception as exc:
            last_exc = exc
            logger.warning("Admin section failed (%s), attempt %s/%s: %s", call_name, attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(0.2 * attempt)
    logger.exception("Admin route section failed after retries: %s (%s)", call_name, last_exc)
    return fallback


def _guess_img_ext(content_type: str, filename: str) -> str:
    c = (content_type or "").lower()
    if c in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if c == "image/png":
        return ".png"
    if c == "image/webp":
        return ".webp"
    lower_name = (filename or "").lower()
    if lower_name.endswith(".jpeg") or lower_name.endswith(".jpg"):
        return ".jpg"
    if lower_name.endswith(".png"):
        return ".png"
    if lower_name.endswith(".webp"):
        return ".webp"
    return ".img"


async def _save_support_attachment(feedback_id: int, upload, role: str) -> str:
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type not in _ALLOWED_SUPPORT_IMAGE_TYPES:
        raise ValueError("Допустимы только JPG/PNG/WEBP изображения.")
    payload = await upload.read()
    if not payload:
        raise ValueError("Файл изображения пустой.")
    if len(payload) > _MAX_SUPPORT_IMAGE_SIZE:
        raise ValueError("Размер изображения не должен превышать 2 МБ.")
    ext = _guess_img_ext(content_type, getattr(upload, "filename", ""))
    dst_dir = get_uploads_root() / "support" / str(feedback_id)
    dst_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{role}_{uuid4().hex}{ext}"
    full_path = dst_dir / filename
    full_path.write_bytes(payload)
    return f"/uploads/support/{feedback_id}/{filename}"


async def _send_feedback_reply_to_telegram(user_id: int, text: str, image_path: str | None = None) -> None:
    bot = get_bot()
    if not bot:
        return
    header = "Ответ от поддержки ASTROV:\n\n"
    body = (text or "").strip()
    final_text = (header + body).strip() if body else "Ответ от поддержки ASTROV."
    await bot.send_message(chat_id=user_id, text=final_text)
    if image_path:
        try:
            abs_path = uploads_public_path_to_fs(image_path)
        except ValueError:
            abs_path = Path()
        if abs_path.exists():
            await bot.send_photo(chat_id=user_id, photo=FSInputFile(path=str(abs_path)))


def _bot_username_for_deep_link() -> str:
    return (get_settings().TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")


def _html_escape_user_dm(text: str) -> str:
    """Текст от админа в личку: безопасный HTML, переносы строк сохраняем."""
    return escape((text or "").strip(), quote=False).replace("\n", "<br/>")


async def _send_admin_user_direct_message(telegram_id: int, text: str) -> tuple[bool, str]:
    """Отправка сообщения пользователю из админки (тот же chat_id, что и telegram_id в личке)."""
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

    bot = get_bot()
    if not bot:
        return False, "Бот не настроен: проверьте TELEGRAM_BOT_TOKEN."
    body = (text or "").strip()
    if not body:
        return False, "Введите текст сообщения."
    if len(body) > _MAX_ADMIN_USER_DM_LEN:
        return False, f"Слишком длинный текст: максимум {_MAX_ADMIN_USER_DM_LEN} символов."
    safe_html = _html_escape_user_dm(body)
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=safe_html,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True, "Сообщение отправлено в Telegram."
    except TelegramForbiddenError:
        uname = _bot_username_for_deep_link()
        extra = ""
        if uname:
            extra = f" Попросите пользователя открыть t.me/{uname}, нажать «Запустить» или написать боту, затем отправьте снова."
        return False, (
            "Telegram не доставил сообщение: пользователь не начинал диалог с ботом или заблокировал бота."
            + extra
        )
    except TelegramBadRequest as exc:
        return False, f"Ошибка Telegram: {exc}"
    except Exception as exc:
        logger.exception("admin send_user telegram failed: %s", exc)
        return False, f"Ошибка отправки: {exc}"


# --- Login / Logout ---

@router.get("/login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    if _admin_authenticated(request):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    try:
        return template_page(templates, request, "admin/login.html", {"error": None})
    except Exception as exc:
        logger.exception("Admin login template render failed, fallback HTML used: %s", exc)
        return HTMLResponse(_ADMIN_LOGIN_FALLBACK_HTML.format(error_html=""), status_code=200)


@router.post("/login")
async def admin_login_post(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    if _admin_authenticated(request):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    if _check_credentials(username, password):
        request.session[_SESSION_ADMIN_KEY] = True
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    try:
        return template_page(
            templates,
            request,
            "admin/login.html",
            {"error": "Неверный логин или пароль"},
            status_code=401,
        )
    except Exception as exc:
        logger.exception("Admin login template render failed on auth error, fallback HTML used: %s", exc)
        return HTMLResponse(
            _ADMIN_LOGIN_FALLBACK_HTML.format(error_html='<div class="err">Неверный логин или пароль</div>'),
            status_code=401,
        )


@router.get("/logout", response_class=RedirectResponse)
async def admin_logout(request: Request):
    request.session.pop(_SESSION_ADMIN_KEY, None)
    return RedirectResponse(url="/admin/login", status_code=302)


@router.post("/sync-revenue", response_class=RedirectResponse)
async def admin_sync_revenue(request: Request, session: AsyncSession = Depends(get_db)):
    """Синхронизировать Revenue из успешных платежей (для старых записей до авто-записи)."""
    redirect = await require_admin(request)
    if redirect:
        return redirect
    try:
        result = await services.backfill_revenue_from_payments(session)
        request.session["flash"] = f"Revenue: добавлено {result['added']}, пропущено {result['skipped']}."
    except Exception as exc:
        logger.exception("Sync revenue failed: %s", exc)
        request.session["flash"] = f"Ошибка синхронизации: {exc}"
    return RedirectResponse(url="/admin/dashboard", status_code=302)


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request):
    if not _admin_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, session: AsyncSession = Depends(get_db)):
    redirect = await require_admin(request)
    if redirect:
        return redirect

    kpis = await _safe_admin_call(
        "kpis",
        lambda: services.get_dashboard_kpis(session),
        {
            "total_users": 0,
            "periodic_users": 0,
            "subscribed": 0,
            "unsubscribed": 0,
            "users_with_balance": 0,
            "bot_stopped_users": 0,
        },
    )
    revenue_totals = await _safe_admin_call(
        "revenue_totals",
        lambda: services.get_revenue_totals(session),
        {"day": 0.0, "week": 0.0, "month": 0.0, "total": 0.0},
    )
    bonus_totals = await _safe_admin_call(
        "bonus_totals",
        lambda: services.get_bonus_totals(session),
        {"day": 0.0, "week": 0.0, "month": 0.0, "total": 0.0},
    )
    revenue_series = await _safe_admin_call("revenue_series", lambda: services.get_revenue_series(session, days=30), [])
    bonus_series = await _safe_admin_call("bonus_series", lambda: services.get_bonus_series(session, days=30), [])
    revenue_series_monthly = await _safe_admin_call(
        "revenue_series_monthly",
        lambda: services.get_revenue_series_monthly(session, months=12),
        [],
    )
    bonus_series_monthly = await _safe_admin_call(
        "bonus_series_monthly",
        lambda: services.get_bonus_series_monthly(session, months=12),
        [],
    )
    tokens_totals = await _safe_admin_call(
        "tokens_totals",
        lambda: services.get_tokens_totals(session),
        {
            "day": {"all": 0, "text": 0, "vision": 0},
            "week": {"all": 0, "text": 0, "vision": 0},
            "month": {"all": 0, "text": 0, "vision": 0},
            "total": {"all": 0, "text": 0, "vision": 0},
        },
    )
    tokens_series = await _safe_admin_call("tokens_series", lambda: services.get_tokens_series(session, days=30), ([], []))
    tokens_text_series, tokens_vision_series = tokens_series
    gender_age = await _safe_admin_call(
        "gender_age",
        lambda: services.get_gender_age_distribution(session),
        {"by_gender": {}, "by_age": {}, "pyramid": []},
    )
    expenses_totals = await _safe_admin_call(
        "expenses_totals",
        lambda: services.get_expenses_totals(session),
        {
            "day": {"by_category": {"commission": 0.0, "advertising": 0.0, "taxes": 0.0, "tokens": 0.0}, "total": 0.0},
            "week": {"by_category": {"commission": 0.0, "advertising": 0.0, "taxes": 0.0, "tokens": 0.0}, "total": 0.0},
            "month": {"by_category": {"commission": 0.0, "advertising": 0.0, "taxes": 0.0, "tokens": 0.0}, "total": 0.0},
            "total": {"by_category": {"commission": 0.0, "advertising": 0.0, "taxes": 0.0, "tokens": 0.0}, "total": 0.0},
        },
    )
    expenses_chart = await _safe_admin_call(
        "expenses_chart",
        lambda: services.get_expenses_by_category_for_chart(session, period="month"),
        [],
    )
    revenue_month = revenue_totals["month"]
    expenses_month = expenses_totals["month"]["total"]
    profit_month = revenue_month - expenses_month
    flash = request.session.pop("flash", None)
    settings = get_settings()
    yookassa_commission_percent = float(getattr(settings, "YOOKASSA_COMMISSION_PERCENT", 0) or 0)
    return template_page(
        templates,
        request,
        "admin/dashboard.html",
        {
            "kpis": kpis,
            "revenue_totals": revenue_totals,
            "bonus_totals": bonus_totals,
            "revenue_series": revenue_series,
            "bonus_series": bonus_series,
            "revenue_series_monthly": revenue_series_monthly,
            "bonus_series_monthly": bonus_series_monthly,
            "tokens_totals": tokens_totals,
            "tokens_text_series": tokens_text_series,
            "tokens_vision_series": tokens_vision_series,
            "gender_age": gender_age,
            "expenses_totals": expenses_totals,
            "expenses_chart": expenses_chart,
            "profit_month": profit_month,
            "flash": flash,
            "yookassa_commission_percent": yookassa_commission_percent,
        },
    )




# --- Users ---

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    session: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    visit_segment: str | None = None,
    visit_sort: str | None = None,
    bot_filter: str | None = None,
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    users_data = await _safe_admin_call(
        "users_list",
        lambda: services.get_users_list(
            session,
            skip=skip,
            limit=limit,
            search=search or "",
            visit_segment=visit_segment or "",
            visit_sort=visit_sort or "",
            bot_filter=bot_filter or "",
        ),
        ([], 0),
    )
    users, total = users_data
    await session.commit()
    pages = (total + limit - 1) // limit if limit else 0
    current_page = (skip // limit) + 1 if limit else 1
    return template_page(
        templates,
        request,
        "admin/users.html",
        {
            "users": users,
            "total": total,
            "skip": skip,
            "limit": limit,
            "search": search or "",
            "visit_segment": (visit_segment or "").strip().lower(),
            "visit_sort": (visit_sort or "").strip().lower(),
            "bot_filter": (bot_filter or "").strip().lower(),
            "pages": pages,
            "current_page": current_page,
        },
    )


@router.get("/users/{telegram_id:int}/edit", response_class=HTMLResponse)
async def admin_user_edit_get(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    user = await _safe_admin_call("user_edit_get", lambda: services.get_user_for_edit(session, telegram_id), None)
    if not user:
        return RedirectResponse(url="/admin/users", status_code=302)
    # Автообновление username/full_name из Telegram, если пусто
    if not (user.get("username") or user.get("full_name")):
        try:
            result = await services.sync_user_from_telegram(session, telegram_id)
            if result.get("ok"):
                await session.commit()
                user = await _safe_admin_call(
                    "user_edit_get",
                    lambda: services.get_user_for_edit(session, telegram_id),
                    user,
                )
        except Exception as exc:
            logger.warning("admin user edit: sync_user_from_telegram failed: %s", exc)
            await session.rollback()
    flash = request.session.pop("flash", None)
    return template_page(
        templates,
        request,
        "admin/user_edit.html",
        {
            "user": user,
            "message": flash,
            "error": None,
            "bot_username": _bot_username_for_deep_link(),
        },
    )


@router.post("/users/{telegram_id:int}/edit", response_class=HTMLResponse)
async def admin_user_edit_post(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    form = await request.form()
    status = form.get("status", "").strip() or None
    subscription_end_date = form.get("subscription_end_date", "").strip() or None
    trial_ends_at = form.get("trial_ends_at", "").strip() or None
    gift_days_str = form.get("gift_days", "").strip()
    gift_days = int(gift_days_str) if gift_days_str.isdigit() else None
    profile_name = (form.get("profile_name") or "").strip()
    profile_birth_date = (form.get("profile_birth_date") or "").strip()
    profile_gender = (form.get("profile_gender") or "").strip()
    profile_birth_city = (form.get("profile_birth_city") or "").strip()
    profile_birth_lat = services._parse_optional_coord(form.get("profile_birth_lat"))
    profile_birth_lon = services._parse_optional_coord(form.get("profile_birth_lon"))
    user = await _safe_admin_call("user_edit_post_preload", lambda: services.get_user_for_edit(session, telegram_id), None)
    if not user:
        return RedirectResponse(url="/admin/users", status_code=302)
    try:
        if profile_name or profile_birth_date or profile_gender or profile_birth_city:
            await services.upsert_profile_for_user(
                session,
                telegram_id,
                name=profile_name,
                birth_date=profile_birth_date,
                gender=profile_gender,
                birth_city=profile_birth_city,
                birth_lat=profile_birth_lat,
                birth_lon=profile_birth_lon,
            )
        await services.update_user_subscription(
            session,
            telegram_id,
            status=status,
            subscription_end_date=subscription_end_date,
            trial_ends_at=trial_ends_at,
            gift_days=gift_days,
        )
        await session.commit()
        user = await _safe_admin_call("user_edit_post_reload", lambda: services.get_user_for_edit(session, telegram_id), user)
        return template_page(
            templates,
            request,
            "admin/user_edit.html",
            {
                "user": user,
                "message": "Изменения сохранены.",
                "error": None,
                "bot_username": _bot_username_for_deep_link(),
            },
        )
    except Exception as e:
        return template_page(
            templates,
            request,
            "admin/user_edit.html",
            {
                "user": user,
                "message": None,
                "error": str(e),
                "bot_username": _bot_username_for_deep_link(),
            },
            status_code=400,
        )


@router.post("/users/{telegram_id:int}/bonus-balance", response_class=RedirectResponse)
async def admin_user_add_bonus_balance(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    form = await request.form()
    amount_raw = (form.get("bonus_amount_rub") or "").strip().replace(",", ".")
    note = (form.get("bonus_note") or "").strip()
    try:
        amount_rub = float(amount_raw)
    except ValueError:
        amount_rub = 0.0
    amount_cents = int(round(amount_rub * 100))
    if amount_cents <= 0:
        request.session["flash"] = "Укажите корректную сумму бонуса (больше 0)."
        return RedirectResponse(url=f"/admin/users/{telegram_id}/edit", status_code=302)
    ok = await services.add_bonus_balance_for_user(
        session=session,
        telegram_id=telegram_id,
        amount_cents=amount_cents,
        note=note,
    )
    if not ok:
        await session.rollback()
        request.session["flash"] = "Не удалось начислить бонус."
        return RedirectResponse(url=f"/admin/users/{telegram_id}/edit", status_code=302)
    await session.commit()
    request.session["flash"] = f"Начислено бонусов: {amount_cents / 100:.2f} ₽."
    return RedirectResponse(url=f"/admin/users/{telegram_id}/edit", status_code=302)


@router.post("/users/{telegram_id:int}/sync-telegram", response_class=RedirectResponse)
async def admin_user_sync_telegram(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Обновить username и full_name пользователя из Telegram Bot API."""
    redirect = await require_admin(request)
    if redirect:
        return redirect
    result = await services.sync_user_from_telegram(session, telegram_id)
    await session.commit()
    if result.get("ok"):
        request.session["flash"] = result.get("message", "Данные обновлены")
    else:
        request.session["flash"] = f"Ошибка: {result.get('message', 'Неизвестная ошибка')}"
    return RedirectResponse(url=f"/admin/users/{telegram_id}/edit", status_code=302)


@router.post("/users/{telegram_id:int}/send-telegram", response_class=RedirectResponse)
async def admin_user_send_telegram(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Сообщение пользователю в личку бота (нужен активный чат: пользователь открыл бота)."""
    redirect = await require_admin(request)
    if redirect:
        return redirect
    user = await services.get_user_for_edit(session, telegram_id)
    if not user:
        request.session["flash"] = "Пользователь не найден."
        return RedirectResponse(url="/admin/users", status_code=302)
    form = await request.form()
    text = (form.get("telegram_message") or "").strip()
    _ok, flash = await _send_admin_user_direct_message(telegram_id, text)
    if not _ok and "заблокировал" in (flash or "").lower():
        await record_bot_unreachable_from_telegram_error(
            session,
            telegram_id=telegram_id,
            error_message="bot was blocked by the user",
        )
    await session.commit()
    request.session["flash"] = flash
    return RedirectResponse(url=f"/admin/users/{telegram_id}/edit", status_code=302)


# --- Support / Appeals ---

@router.get("/support", response_class=HTMLResponse)
async def admin_support_list(
    request: Request,
    session: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    status_filter: str = "",
    search: str = "",
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    items, total = await _safe_admin_call(
        "support_list",
        lambda: services.get_feedback_list(
            session,
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            search=search,
        ),
        ([], 0),
    )
    pages = (total + limit - 1) // limit if limit else 0
    current_page = (skip // limit) + 1 if limit else 1
    return template_page(
        templates,
        request,
        "admin/support.html",
        {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
            "search": search,
            "status_filter": status_filter,
            "pages": pages,
            "current_page": current_page,
        },
    )


@router.get("/support/unread-count")
async def admin_support_unread_count(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return JSONResponse({"ok": False, "count": 0}, status_code=401)
    count = await _safe_admin_call(
        "support_unread_count",
        lambda: services.get_feedback_unread_count(session),
        0,
    )
    return JSONResponse({"ok": True, "count": int(count or 0)})


@router.get("/support/user/{telegram_id:int}", response_class=HTMLResponse)
async def admin_support_user_thread(
    request: Request,
    telegram_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    thread = await _safe_admin_call(
        "support_user_thread",
        lambda: services.get_feedback_user_thread(session, telegram_id),
        None,
    )
    if not thread:
        return RedirectResponse(url="/admin/support", status_code=302)
    return template_page(
        templates,
        request,
        "admin/support_user_thread.html",
        {"thread": thread},
    )


@router.get("/support/{feedback_id:int}", response_class=HTMLResponse)
async def admin_support_details(
    request: Request,
    feedback_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    details = await _safe_admin_call(
        "support_details",
        lambda: services.get_feedback_details(session, feedback_id),
        None,
    )
    if not details:
        return RedirectResponse(url="/admin/support", status_code=302)
    await services.set_feedback_status(session, feedback_id, read_state="read")
    await session.commit()
    details = await services.get_feedback_details(session, feedback_id)
    return template_page(
        templates,
        request,
        "admin/support_detail.html",
        {"details": details, "error": None, "message": request.session.pop("flash", None)},
    )


@router.post("/support/{feedback_id:int}/status", response_class=RedirectResponse)
async def admin_support_set_status(
    request: Request,
    feedback_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    form = await request.form()
    read_state = (form.get("read_state", "") or "").strip().lower()
    resolved_state = (form.get("resolved_state", "") or "").strip().lower()
    updated = await services.set_feedback_status(
        session,
        feedback_id=feedback_id,
        read_state=read_state if read_state in {"read", "unread"} else None,
        resolved_state=resolved_state if resolved_state in {"resolved", "unresolved"} else None,
    )
    await session.commit()
    request.session["flash"] = "Статус обновлен." if updated else "Не удалось обновить статус."
    return RedirectResponse(url=f"/admin/support/{feedback_id}", status_code=302)


@router.post("/support/{feedback_id:int}/reply", response_class=RedirectResponse)
async def admin_support_reply(
    request: Request,
    feedback_id: int,
    session: AsyncSession = Depends(get_db),
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    form = await request.form()
    reply_text = (form.get("reply_text", "") or "").strip()
    mark_resolved = str(form.get("mark_resolved", "") or "").strip().lower() in {"1", "true", "on", "yes"}
    upload = form.get("image")
    if not reply_text and not upload:
        request.session["flash"] = "Добавьте текст ответа или изображение."
        return RedirectResponse(url=f"/admin/support/{feedback_id}", status_code=302)

    feedback_details = await services.get_feedback_details(session, feedback_id)
    if not feedback_details:
        request.session["flash"] = "Обращение не найдено."
        return RedirectResponse(url="/admin/support", status_code=302)

    image_path: str | None = None
    if upload and getattr(upload, "filename", ""):
        try:
            image_path = await _save_support_attachment(feedback_id, upload, role="admin")
            session.add(
                FeedbackAttachment(
                    feedback_id=feedback_id,
                    role="admin",
                    image_path=image_path,
                )
            )
        except ValueError as exc:
            request.session["flash"] = str(exc)
            return RedirectResponse(url=f"/admin/support/{feedback_id}", status_code=302)

    if reply_text:
        await services.add_feedback_reply(session, feedback_id, reply_text)

    if mark_resolved:
        await services.set_feedback_status(session, feedback_id, read_state="read", resolved_state="resolved")
    else:
        await services.set_feedback_status(session, feedback_id, read_state="read")

    await session.commit()

    try:
        await _send_feedback_reply_to_telegram(
            user_id=int(feedback_details["feedback"].user_id),
            text=reply_text,
            image_path=image_path,
        )
        request.session["flash"] = "Ответ отправлен пользователю."
    except Exception as exc:
        logger.exception("Failed to send support reply to Telegram: %s", exc)
        request.session["flash"] = "Ответ сохранен, но не удалось отправить в Telegram."
    return RedirectResponse(url=f"/admin/support/{feedback_id}", status_code=302)


# --- Stats (usage by type) ---

@router.get("/stats", response_class=HTMLResponse)
async def admin_stats(request: Request, session: AsyncSession = Depends(get_db)):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    usage = await _safe_admin_call("stats_usage_by_type", lambda: services.get_usage_by_type(session), {})
    type_labels = {"tarot": "Таро", "vision": "Сканер", "dream": "Сны", "numerology": "Нумерология"}
    usage_with_labels = [(type_labels.get(k, k), usage.get(k, 0)) for k in type_labels]
    return template_page(
        templates,
        request,
        "admin/stats.html",
        {"usage": usage, "usage_with_labels": usage_with_labels},
    )


# --- Finance ---

@router.get("/finance", response_class=HTMLResponse)
async def admin_finance(
    request: Request,
    session: AsyncSession = Depends(get_db),
    year: int | None = None,
    month: int | None = None,
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    from datetime import date as date_type
    today = date_type.today()
    y = year or today.year
    m = month or today.month
    revenue_totals = await _safe_admin_call(
        "finance_revenue_totals",
        lambda: services.get_revenue_totals(session),
        {"day": 0.0, "week": 0.0, "month": 0.0, "total": 0.0},
    )
    bonus_totals = await _safe_admin_call(
        "finance_bonus_totals",
        lambda: services.get_bonus_totals(session),
        {"day": 0.0, "week": 0.0, "month": 0.0, "total": 0.0},
    )
    revenue_series = await _safe_admin_call("finance_revenue_series", lambda: services.get_revenue_series(session, days=30), [])
    bonus_series = await _safe_admin_call("finance_bonus_series", lambda: services.get_bonus_series(session, days=30), [])
    revenue_series_monthly = await _safe_admin_call(
        "finance_revenue_series_monthly",
        lambda: services.get_revenue_series_monthly(session, months=12),
        [],
    )
    bonus_series_monthly = await _safe_admin_call(
        "finance_bonus_series_monthly",
        lambda: services.get_bonus_series_monthly(session, months=12),
        [],
    )
    tokens_totals = await _safe_admin_call(
        "finance_tokens_totals",
        lambda: services.get_tokens_totals(session),
        {
            "day": {"all": 0, "text": 0, "vision": 0},
            "week": {"all": 0, "text": 0, "vision": 0},
            "month": {"all": 0, "text": 0, "vision": 0},
            "total": {"all": 0, "text": 0, "vision": 0},
        },
    )
    tokens_text_series, tokens_vision_series = await _safe_admin_call(
        "finance_tokens_series",
        lambda: services.get_tokens_series(session, days=30),
        ([], []),
    )
    expenses_table = await _safe_admin_call("finance_expenses_table", lambda: services.get_expenses_table_data(session, y, m), [])
    settings = get_settings()
    yookassa_commission_percent = float(getattr(settings, "YOOKASSA_COMMISSION_PERCENT", 0) or 0)
    return template_page(
        templates,
        request,
        "admin/finance.html",
        {
            "revenue_totals": revenue_totals,
            "bonus_totals": bonus_totals,
            "revenue_series": revenue_series,
            "bonus_series": bonus_series,
            "revenue_series_monthly": revenue_series_monthly,
            "bonus_series_monthly": bonus_series_monthly,
            "tokens_totals": tokens_totals,
            "tokens_text_series": tokens_text_series,
            "tokens_vision_series": tokens_vision_series,
            "expenses_table": expenses_table,
            "table_year": y,
            "table_month": m,
            "yookassa_commission_percent": yookassa_commission_percent,
        },
    )


# --- Token stats (AI usage) ---

@router.get("/token-stats", response_class=HTMLResponse)
async def admin_token_stats(
    request: Request,
    session: AsyncSession = Depends(get_db),
    period: str = "week",
    skip: int = 0,
    limit: int = 50,
    user_id: int | None = None,
    feature: str | None = None,
):
    redirect = await require_admin(request)
    if redirect:
        return redirect
    stats = await _safe_admin_call(
        "token_usage_stats",
        lambda: services.get_token_usage_stats(session, period=period, skip=skip, limit=limit, user_id_filter=user_id, feature_filter=feature),
        {"period": period, "total_rub": 0, "total_tokens": 0, "daily": [], "by_feature": [], "by_provider": [], "details": []},
    )
    total_details = await _safe_admin_call(
        "token_usage_details_count",
        lambda: services.get_token_usage_details_count(session, period=period, user_id_filter=user_id, feature_filter=feature),
        0,
    )
    exchange_rate = await _safe_admin_call("exchange_rate", lambda: services.get_exchange_rate(session), 95.0)
    exchange_rate_updated_at = await _safe_admin_call(
        "exchange_rate_updated_at",
        lambda: services.get_exchange_rate_updated_at(session),
        None,
    )
    return template_page(
        templates,
        request,
        "admin/token_stats.html",
        {
            "stats": stats,
            "total_details": total_details,
            "period": period,
            "skip": skip,
            "limit": limit,
            "user_id_filter": user_id,
            "feature_filter": feature,
            "exchange_rate": exchange_rate,
            "exchange_rate_updated_at": exchange_rate_updated_at,
        },
    )


@router.get("/api/token-stats")
async def admin_api_token_stats(
    request: Request,
    session: AsyncSession = Depends(get_db),
    period: str = "week",
    skip: int = 0,
    limit: int = 50,
    user_id: int | None = None,
    feature: str | None = None,
):
    """JSON для пагинации и фильтров страницы токенов."""
    redirect = await require_admin(request)
    if redirect:
        return RedirectResponse(url="/admin/login", status_code=302)
    stats = await _safe_admin_call(
        "token_usage_stats",
        lambda: services.get_token_usage_stats(session, period=period, skip=skip, limit=limit, user_id_filter=user_id, feature_filter=feature),
        {"period": period, "total_rub": 0, "total_tokens": 0, "daily": [], "by_feature": [], "by_provider": [], "details": []},
    )
    total_details = await _safe_admin_call(
        "token_usage_details_count",
        lambda: services.get_token_usage_details_count(session, period=period, user_id_filter=user_id, feature_filter=feature),
        0,
    )
    from fastapi.responses import JSONResponse
    return JSONResponse({"stats": stats, "total_details": total_details})


@router.get("/api/token-stats/csv")
async def admin_token_stats_csv(
    request: Request,
    session: AsyncSession = Depends(get_db),
    period: str = "week",
    user_id: int | None = None,
    feature: str | None = None,
):
    """Экспорт детализации токенов в CSV."""
    redirect = await require_admin(request)
    if redirect:
        return RedirectResponse(url="/admin/login", status_code=302)
    stats = await _safe_admin_call(
        "token_usage_stats",
        lambda: services.get_token_usage_stats(
            session, period=period, skip=0, limit=50000,
            user_id_filter=user_id, feature_filter=feature,
        ),
        {"details": []},
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["created_at", "user_id", "feature_type", "provider", "model", "total_tokens", "cost_rub"])
    for d in stats.get("details", []):
        writer.writerow([
            d.get("created_at") or "",
            d.get("user_id") or "",
            d.get("feature_type") or "",
            d.get("provider") or "",
            d.get("model") or "",
            d.get("total_tokens") or 0,
            d.get("cost_rub") or 0,
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=token-stats.csv"},
    )


@router.post("/finance/expenses")
async def admin_finance_expenses_save(request: Request, session: AsyncSession = Depends(get_db)):
    """Сохранить траты из таблицы (комиссии, реклама, налоги по дням)."""
    redirect = await require_admin(request)
    if redirect:
        return redirect
    from datetime import datetime as dt
    form = await request.form()
    for key, value in form.items():
        if not key.startswith("expense_") or "_" not in key:
            continue
        parts = key.replace("expense_", "").split("_")
        if len(parts) != 2:
            continue
        date_str, category = parts[0], parts[1]
        if category not in ("commission", "advertising", "taxes"):
            continue
        try:
            amount = float(str(value).replace(",", ".").strip() or "0")
        except ValueError:
            amount = 0.0
        try:
            period_date = dt.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        await services.set_expense_for_date(session, period_date, category, amount)
    await session.commit()
    year = form.get("_year")
    month = form.get("_month")
    if year and month:
        return RedirectResponse(url=f"/admin/finance?year={year}&month={month}", status_code=302)
    return RedirectResponse(url="/admin/finance", status_code=302)
