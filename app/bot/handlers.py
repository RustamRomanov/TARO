"""Bot message and callback handlers."""
import json
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    ChatMemberUpdated,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultPhoto,
    InlineQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.config import get_settings
from app.db.models import Feedback
from app.db.session import async_session_factory
from app.services.cache import (
    delete_json as cache_delete_json,
    get_json as cache_get_json,
    set_json as cache_set_json,
)
from app.services.limits import _ensure_user
from app.services.referral import store_pending_referrer
from app.services.user_bot_chat_status import record_bot_chat_member_status

logger = logging.getLogger(__name__)

router = Router(name="main")

# Ожидание текста обращения после /support (TTL, сек.)
_SUPPORT_PENDING_TTL_SECONDS = 900


def _support_pending_cache_key(telegram_id: int) -> str:
    return f"bot_support_pending:{telegram_id}"


# Текст кнопки reply-клавиатуры под полем ввода (должен совпадать с обработчиком ниже).
SUPPORT_REPLY_BUTTON_TEXT = "Поддержка"


def _main_private_reply_keyboard(*, web_app_url: str) -> ReplyKeyboardMarkup:
    """Кнопки под полем ввода в личке: Mini App и поддержка."""
    rows: list[list[KeyboardButton]] = []
    base = (web_app_url or "").strip().rstrip("/")
    if base:
        rows.append(
            [KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=base))],
        )
    rows.append([KeyboardButton(text=SUPPORT_REPLY_BUTTON_TEXT)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Сообщение…",
    )


@router.my_chat_member(F.chat.type == ChatType.PRIVATE)
async def on_private_my_chat_member(event: ChatMemberUpdated) -> None:
    """Фиксируем блокировку / возврат к боту: Telegram шлёт ChatMemberUpdated в личке."""
    nm = event.new_chat_member
    status_attr = getattr(nm, "status", None)
    status = status_attr.value if hasattr(status_attr, "value") else str(status_attr or "")
    fu = event.from_user
    username = fu.username if fu else None
    full_name = ((fu.full_name or "").strip() or None) if fu else None
    telegram_id = int(event.chat.id)
    try:
        async with async_session_factory() as session:
            await record_bot_chat_member_status(
                session,
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                new_status=status,
            )
            await session.commit()
    except Exception:
        logger.exception("my_chat_member: failed to persist bot status for user_id=%s", telegram_id)


# Корень проекта (где лежит astrov.jpg)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start: send photo, caption and Web App button."""
    if message.from_user:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            arg = parts[1].strip()
            if arg.startswith("ref_"):
                try:
                    ref_id = int(arg[4:])
                    if ref_id > 0 and ref_id != message.from_user.id:
                        await store_pending_referrer(message.from_user.id, ref_id)
                except ValueError:
                    pass

    settings = get_settings()
    web_app_url = (settings.APP_URL or "").rstrip("/")

    text = (
        "<b>Рад приветствовать вас лично.</b> 🤝\n\n"
        "Вы сделали правильный выбор. Моя система уже настроена "
        "и готова к работе.\n\n"
        "Под полем ввода закреплены кнопки: открыть приложение "
        f"(если задан адрес сервера) и <b>«{SUPPORT_REPLY_BUTTON_TEXT}»</b> для связи с поддержкой. "
        "Также можно отправить команду <b>/support</b> "
        "или выбрать команду в меню у поля ввода.\n\n"
        "<b>Используйте кнопки под полем ввода.</b> 👇"
    )

    if not web_app_url:
        caption = (
            text
            + "\n\n(Кнопка приложения не показана: в настройках сервера не задан APP_URL. "
            "Добавьте переменную APP_URL на хостинге, например в Railway в разделе Variables.)"
        )
    else:
        caption = text

    reply_kb = _main_private_reply_keyboard(web_app_url=web_app_url or "")

    # Фото отправляем в любом случае; если нет APP_URL - хотя бы приветствие с фото
    photo_path = None
    for name in ("astrov.jpg", "Astrov.jpeg", "astrov.jpeg", "Astrov.jpg"):
        p = PROJECT_ROOT / name
        if p.is_file():
            photo_path = p
            break
    try:
        if photo_path:
            photo = FSInputFile(photo_path)
            await message.answer_photo(
                photo=photo,
                caption=caption,
                reply_markup=reply_kb,
                parse_mode="HTML",
            )
        else:
            await message.answer(text=caption, reply_markup=reply_kb, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка с фото: {e}")
        await message.answer(text=caption, reply_markup=reply_kb, parse_mode="HTML")


async def _send_support_pending_prompt(message: Message) -> None:
    """Включает режим ожидания текста обращения (после /support или кнопки «Поддержка»)."""
    user = message.from_user
    if user is None or getattr(user, "is_bot", False):
        return
    key = _support_pending_cache_key(user.id)
    await cache_set_json(key, {"pending": True}, ttl_seconds=_SUPPORT_PENDING_TTL_SECONDS)
    await message.answer(
        "Чтобы написать в поддержку, пришлите <b>следующим одним сообщением</b> ваш текст: "
        "вопрос, описание проблемы или предложение.\n\n"
        "Если передумали, отправьте /cancel.\n\n"
        "Свободные сообщения боту без команды /support в поддержку не принимаются.",
        parse_mode="HTML",
    )


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    """Пользователь явно запрашивает диалог с поддержкой: следующий текст уйдёт в Feedback."""
    await _send_support_pending_prompt(message)


@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.text == SUPPORT_REPLY_BUTTON_TEXT,
)
async def cmd_support_reply_keyboard_button(message: Message) -> None:
    """Та же логика, что и /support: нажатие кнопки под полем ввода в личке."""
    await _send_support_pending_prompt(message)


@router.message(Command("cancel"))
async def cmd_cancel_support(message: Message) -> None:
    """Сбрасывает ожидание текста обращения после /support."""
    user = message.from_user
    if user is None or getattr(user, "is_bot", False):
        return
    key = _support_pending_cache_key(user.id)
    had = await cache_get_json(key)
    await cache_delete_json(key)
    if had:
        await message.answer(
            "Готово. Обращение не отправлено. Чтобы написать позже, снова нажмите «Поддержка» или отправьте /support."
        )
    else:
        await message.answer(
            "Сейчас нечего отменять. Чтобы написать в поддержку, нажмите «Поддержка» под полем ввода или отправьте /support."
        )


@router.message(F.web_app_data)
async def handle_web_app_data(message: Message) -> None:
    """Данные из Mini App (sendData). Не отвечаем в чат: иначе дублируется логика API и сбивает пользователя."""
    raw = getattr(message.web_app_data, "data", None) or ""
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict) and data:
        logger.debug("web_app_data keys=%s user=%s", list(data.keys())[:12], message.from_user.id if message.from_user else None)


@router.message(
    F.chat.type == ChatType.PRIVATE,
    F.text,
    ~F.text.startswith("/"),
)
async def handle_private_text_after_support_or_reject(message: Message) -> None:
    """Текст в личку принимается только после /support; иначе просим использовать команду."""
    user = message.from_user
    if user is None or getattr(user, "is_bot", False):
        return
    text = (message.text or "").strip()
    if not text:
        return
    telegram_id = user.id
    username = user.username
    full_name = (user.full_name or "").strip() or None
    key = _support_pending_cache_key(telegram_id)
    pending = await cache_get_json(key)
    if not pending:
        # Не отвечаем: иначе бот «перебивает» ответы на расклады, реплаи и любой текст вне сценария /support.
        return
    try:
        async with async_session_factory() as session:
            await _ensure_user(session, telegram_id, username=username, full_name=full_name)
            feedback = Feedback(user_id=telegram_id, message=text, status="unread_unresolved")
            session.add(feedback)
            await session.commit()
    except Exception:
        logger.exception("Failed to persist Feedback from Telegram bot private message")
        await message.answer(
            "Не удалось сохранить сообщение. Попробуйте позже или отправьте обращение через приложение."
        )
        return
    await cache_delete_json(key)
    await message.answer(
        "Спасибо! Сообщение передано в поддержку. Мы ответим в ближайшее время."
    )


@router.inline_query(F.query.startswith("share_"))
async def handle_inline_share(inline_query: InlineQuery) -> None:
    """Inline: отправка расклада выбранному получателю (картинка + текст + кнопка)."""
    query = (inline_query.query or "").strip()
    token = query[6:].strip() if query.startswith("share_") else ""
    cache_key = f"tarot_share:{token}"
    logger.info("Inline share: query=%r token=%r key=%s", query[:80], token[:20] if token else None, cache_key)
    if not token:
        await inline_query.answer(results=[], cache_time=1)
        return
    try:
        cached = await cache_get_json(cache_key)
    except Exception as e:
        logger.exception("Inline share cache get failed: %s", e)
        cached = None
    if not isinstance(cached, dict):
        logger.warning("Inline share cache miss: key=%s", cache_key)
        await inline_query.answer(
            results=[],
            cache_time=1,
            switch_pm_text="Токен устарел. Откройте приложение и попробуйте снова.",
            switch_pm_parameter="tarot",
        )
        return
    first_url = cached.get("first_url") or ""
    caption = (cached.get("caption") or "").strip() or "Расклад от ASTROV"
    caption_limit = 1024
    if len(caption) > caption_limit:
        footer = 'Ответы на свои вопросы ищи тут 👉 <a href="https://t.me/astrov_bot">ASTROV</a>'
        reserve = len("\n\n") + 3 + len(footer)  # "..."
        max_content = caption_limit - reserve
        if max_content > 50:
            truncated = (caption[: max_content - 3].rsplit("\n", 1)[0] or caption[: max_content - 3]) + "..."
            caption = truncated + "\n\n" + footer
        else:
            caption = caption[: caption_limit - len(footer) - 5] + "...\n\n" + footer
    try:
        if first_url:
            result = InlineQueryResultPhoto(
                id=token[:64],
                photo_url=first_url,
                thumbnail_url=first_url,
                caption=caption,
                parse_mode="HTML",
            )
            logger.info("Inline share: returning photo result url=%s", first_url[:80])
            await inline_query.answer(results=[result], cache_time=1)
        else:
            from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

            logger.info("Inline share: no photo_url, returning Article")
            result = InlineQueryResultArticle(
                id=token[:64],
                title="Расклад от ASTROV",
                description=caption[:100] + "..." if len(caption) > 100 else caption,
                input_message_content=InputTextMessageContent(message_text=caption, parse_mode="HTML"),
            )
            await inline_query.answer(results=[result], cache_time=1)
    except Exception as e:
        logger.exception("Inline share answer failed: %s", e)
        try:
            await inline_query.answer(
                results=[],
                cache_time=1,
                switch_pm_text="Ошибка. Попробуйте снова.",
                switch_pm_parameter="tarot",
            )
        except Exception:
            pass
