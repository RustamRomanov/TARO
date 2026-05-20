"""Точка входа: FastAPI + бот (webhook в продакшене или polling локально)."""
import asyncio
import hmac
import logging
import os
import sys
import time
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.admin_panel.routes import router as admin_router
from app.api import router as api_router
from app.bot.main import get_bot, get_dispatcher, setup_bot_commands
from app.core.config import get_settings
from app.core.uploads_dir import get_uploads_root
from app.db.session import async_session_factory, init_db
from app.services.subscription_expiry_notifications import run_subscription_expiry_notifications
from app.services.runtime_metrics import record_request, snapshot as runtime_metrics_snapshot

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram/webhook"


async def _run_bot_polling() -> None:
    """Запуск бота в режиме long polling (один инстанс, иначе Conflict)."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN не задан; бот не запущен.")
        return
    bot = get_bot()
    dp = get_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook сброшен. Пауза 2 с перед polling (чтобы другой инстанс успел отпустить getUpdates)...")
    await asyncio.sleep(2)
    logger.info("Запуск polling (режим getUpdates). В проде лучше задать WEBHOOK_BASE_URL и использовать webhook.)")
    await setup_bot_commands()
    await dp.start_polling(bot)


async def _setup_webhook() -> None:
    """Установить webhook URL в Telegram (только один инстанс получает обновления)."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not settings.WEBHOOK_BASE_URL:
        return
    bot = get_bot()
    base = settings.WEBHOOK_BASE_URL.rstrip("/")
    url = f"{base}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    webhook_secret = (settings.TELEGRAM_WEBHOOK_SECRET or "").strip()
    if webhook_secret:
        await bot.set_webhook(url, secret_token=webhook_secret)
    else:
        await bot.set_webhook(url)
    logger.info("Webhook установлен: %s", url)
    await setup_bot_commands()


async def _run_bot() -> None:
    """Webhook в продакшене (WEBHOOK_BASE_URL задан) или polling локально - только один режим, иначе Conflict."""
    env_val = os.environ.get("WEBHOOK_BASE_URL") or ""
    logger.info("WEBHOOK_BASE_URL в os.environ: задан=%s (длина %d)", bool(env_val.strip()), len(env_val))
    settings = get_settings()
    webhook_url = (settings.WEBHOOK_BASE_URL or "").strip()
    logger.info("WEBHOOK_BASE_URL из Settings: задан=%s (длина %d)", bool(webhook_url), len(webhook_url))
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN не задан; бот не запущен.")
        return
    if webhook_url:
        await _setup_webhook()
        logger.info("Бот в режиме webhook (обновления на POST %s). Polling не запущен.", WEBHOOK_PATH)
        return
    logger.info("WEBHOOK_BASE_URL не задан или пустой - запуск в режиме polling.")
    await _run_bot_polling()


async def _run_subscription_expiry_dispatcher() -> None:
    """Background dispatcher: sends tariff expiry reminders in scheduled window."""
    while True:
        try:
            async with async_session_factory() as session:
                result = await run_subscription_expiry_notifications(session, limit_users=1500)
                await session.commit()
            sent = int(result.get("sent", 0)) if isinstance(result, dict) else 0
            skipped = int(result.get("skipped", 0)) if isinstance(result, dict) else 0
            if sent:
                logger.info("Subscription expiry notices dispatched: sent=%s skipped=%s", sent, skipped)
        except Exception as exc:
            logger.warning("Subscription expiry dispatcher tick failed: %s", exc)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запуск бота в фоне при старте приложения."""
    try:
        from app.core.templates_path import resolve_templates_directory

        tpl_root = resolve_templates_directory()
        users_mark = tpl_root / "admin" / "users.html"
        if users_mark.is_file():
            logger.info("Jinja шаблоны: %s", tpl_root)
            from fastapi.templating import Jinja2Templates

            _warm = Jinja2Templates(directory=str(tpl_root))
            for _tpl_name in ("admin/dashboard.html", "admin/users.html"):
                try:
                    _warm.get_template(_tpl_name)
                except Exception:
                    logger.exception("Jinja: предзагрузка шаблона %s (каталог %s)", _tpl_name, tpl_root)
        else:
            logger.error(
                "Jinja: не найден %s. Задайте ASTROV_TEMPLATES_DIR или проверьте COPY templates в образе.",
                users_mark,
            )
    except Exception as exc:
        logger.warning("Проверка каталога шаблонов: %s", exc)
    try:
        await init_db()
        logger.info("DB init/create_all completed.")
    except Exception as exc:
        logger.exception("DB init failed: %s", exc)
    bot_task = asyncio.create_task(_run_bot())
    sub_expiry_task = asyncio.create_task(_run_subscription_expiry_dispatcher())
    yield
    bot_task.cancel()
    sub_expiry_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    try:
        await sub_expiry_task
    except asyncio.CancelledError:
        pass


# --- FastAPI app ---

app = FastAPI(
    title="TARO API",
    lifespan=lifespan,
)

settings = get_settings()

def _build_cors_origins() -> list[str]:
    raw = (settings.CORS_ALLOWED_ORIGINS or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    app_url = (settings.APP_URL or "").strip()
    if app_url:
        return [app_url]
    if settings.DEBUG:
        return ["*"]
    return []


_cors_origins = _build_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or [],
    allow_credentials=bool(_cors_origins) and ("*" not in _cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

_admin_session_secret = (settings.ADMIN_SESSION_SECRET or "").strip()
if not _admin_session_secret:
    fallback_password_secret = (settings.ADMIN_PASSWORD or "").strip()
    if fallback_password_secret:
        _admin_session_secret = fallback_password_secret
        logger.warning(
            "ADMIN_SESSION_SECRET is not set, fallback to ADMIN_PASSWORD as session secret. "
            "Set ADMIN_SESSION_SECRET in production for stronger isolation."
        )
    elif settings.DEBUG:
        _admin_session_secret = "astrov-admin-secret-change-me"
    else:
        logger.error(
            "Задайте ADMIN_SESSION_SECRET или ADMIN_PASSWORD в окружении, иначе сессии админки и приложение не стартуют."
        )
        raise RuntimeError(
            "ADMIN_SESSION_SECRET or ADMIN_PASSWORD is required in non-debug mode. "
            "Set either variable in Railway/env."
        )

app.add_middleware(
    SessionMiddleware,
    secret_key=_admin_session_secret,
)

SLOW_REQUEST_WARN_MS = 1200.0


@app.middleware("http")
async def _no_cache_frontend_assets(request: Request, call_next):
    """Cache policy: HTML no-cache, static assets cached for faster Telegram WebView loads."""
    path = request.url.path or ""
    response = await call_next(request)
    if path == "/" or path == "/index.html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    if path.startswith("/assets/") or path.endswith(".js") or path.endswith(".css") or path.endswith(".woff2"):
        # Vite assets are content-hashed -> safe to cache aggressively.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    if path.startswith("/tarot-spreads/") or path.endswith(".png") or path.endswith(".jpg") or path.endswith(".jpeg") or path.endswith(".webp"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.middleware("http")
async def _runtime_observability(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
        return response
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        route_path = request.url.path or "/"
        method = request.method or "GET"
        now_ms = int(time.time() * 1000)
        record_request(
            route=route_path,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            now_ms=now_ms,
        )
        if status_code >= 500:
            logger.warning(
                "runtime_alert type=http_5xx method=%s path=%s status=%s duration_ms=%.1f",
                method,
                route_path,
                status_code,
                duration_ms,
            )
        elif duration_ms >= SLOW_REQUEST_WARN_MS:
            logger.warning(
                "runtime_alert type=slow_http method=%s path=%s status=%s duration_ms=%.1f threshold_ms=%.1f",
                method,
                route_path,
                status_code,
                duration_ms,
                SLOW_REQUEST_WARN_MS,
            )


app.include_router(api_router, prefix="/api")


@app.get("/api/system/runtime-metrics", include_in_schema=False)
async def runtime_metrics(request: Request, top: int = 30):
    settings = get_settings()
    expected_secret = (settings.BILLING_CRON_SECRET or "").strip()
    if not expected_secret:
        if settings.DEBUG:
            payload = runtime_metrics_snapshot(top_limit=max(1, min(int(top), 100)), now_ms=int(time.time() * 1000))
            return payload
        return JSONResponse(status_code=503, content={"detail": "Runtime metrics endpoint is not configured."})
    provided = (request.headers.get("X-Billing-Secret") or "").strip()
    if provided != expected_secret:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    payload = runtime_metrics_snapshot(top_limit=max(1, min(int(top), 100)), now_ms=int(time.time() * 1000))
    return payload


def _ru_validation_msg(msg: str) -> str:
    """Replace known English validation messages with Russian (e.g. for Telegram init_data)."""
    if not msg:
        return msg
    lower = msg.lower()
    if "pattern" in lower and ("match" in lower or "expected" in lower):
        return "Данные авторизации не прошли проверку. Откройте приложение из Telegram заново."
    if "invalid" in lower or "missing init_data" in lower or "unauthorized" in lower:
        return "Откройте приложение из Telegram заново."
    return msg


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return 422 with Russian messages for auth/pattern errors."""
    errs = getattr(exc, "errors", None)
    details = errs() if callable(errs) else (errs or [])
    out = []
    for e in details:
        d = dict(e) if isinstance(e, dict) else {}
        msg = d.get("msg") or d.get("message") or ""
        d["msg"] = _ru_validation_msg(str(msg))
        out.append(d)
    return JSONResponse(status_code=422, content={"detail": out})

# Статика темы админки (тёмная тема Astrov)
_admin_static = Path(__file__).resolve().parent / "static" / "admin"
if _admin_static.exists():
    app.mount("/admin-theme", StaticFiles(directory=str(_admin_static)), name="admin_theme")

# User-uploaded assets (аватары, support; см. ASTROV_UPLOADS_DIR + Railway Volume)
_uploads_static = get_uploads_root()
app.mount("/uploads", StaticFiles(directory=str(_uploads_static)), name="uploads")

# Редирект /admin -> /admin/
@app.get("/admin", include_in_schema=False)
async def admin_redirect():
    return RedirectResponse(url="/admin/", status_code=302)

app.include_router(admin_router, prefix="/admin")

# Telegram webhook: приём обновлений (только когда WEBHOOK_BASE_URL задан в продке)
@app.post(WEBHOOK_PATH, include_in_schema=False)
async def telegram_webhook(request: Request):
    """Принимает POST от Telegram с обновлениями; не вызывать getUpdates (polling) при работе по webhook."""
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN or not settings.WEBHOOK_BASE_URL:
        return JSONResponse({"ok": False, "error": "webhook not configured"}, status_code=503)
    expected_secret = (settings.TELEGRAM_WEBHOOK_SECRET or "").strip()
    if expected_secret:
        provided_secret = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    # Диагностика: логируем тип обновления (inline_query и т.д.)
    update_type = "unknown"
    if "inline_query" in body:
        update_type = "inline_query"
        q = body.get("inline_query", {}).get("query", "")[:50]
        logger.info("Webhook: inline_query query=%r", q)
    elif "message" in body:
        update_type = "message"
    elif "callback_query" in body:
        update_type = "callback_query"
    else:
        update_type = next((k for k in ("chosen_inline_result", "channel_post") if k in body), "other")
    logger.info("Webhook: update_type=%s", update_type)
    bot = get_bot()
    dp = get_dispatcher()
    try:
        await dp.feed_webhook_update(bot, body)
    except Exception as exc:
        logger.exception("Webhook update failed: %s", exc)
        return JSONResponse({"ok": False}, status_code=500)
    return {"ok": True}

# Статика фронтенда (production / Railway)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("admin"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        fp = _frontend_dist / full_path
        if fp.is_file():
            return FileResponse(fp)
        return FileResponse(
            _frontend_dist / "index.html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )
else:
    @app.get("/")
    async def root():
        return {"status": "ok", "app": "Astrov"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
