"""Legacy tarot API routes (draw, validate, share)."""
from __future__ import annotations

import json
import logging
import random
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tarot_routes import _find_visual_description
from app.core.config import get_settings
from app.core.security import get_telegram_user_id_from_init_data
from app.db.models import History, HistoryType
from app.db.session import get_db
from app.services.ai_client import AIServiceClient
from app.services.cache import set_json as cache_set_json
from app.services.gender import gender_hint_for_prompt
from app.services.limits import check_limits, increment_daily
from app.services.prompts.tarot_rw import (
    TAROT_SINGLE_CARD_SYSTEM,
    build_tarot_single_card_user_prompt,
    get_position_name,
    get_tarot_card_type,
    resolve_spread_position_index,
)

router = APIRouter()
ai_client = AIServiceClient()
logger = logging.getLogger(__name__)

BOT_LINK = "https://t.me/astrov_bot"

SPREAD_NAMES_RU: dict[str, str] = {
    "single": "Карта дня",
    "three_cards": "3 карты",
    "financial": "Финансы",
    "six_cards": "Отношения",
    "ten_cards": "Кельтский крест",
}

ARCANA = [
    "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
    "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
    "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star", "The Moon", "The Sun",
    "Judgement", "The World",
]


class TarotRequest(BaseModel):
    deck: str = "classic"
    question: str = ""
    card_name: str = ""
    card_id: str = ""
    position: int | None = None
    total: int | None = None
    position_name: str | None = None
    is_reversed: bool = False
    init_data: str = ""
    profile_id: int | None = None
    personalize: bool = False


class TarotResponse(BaseModel):
    card_name: str
    interpretation: str


class ValidateQuestionRequest(BaseModel):
    question: str = ""
    spread: str = "basic"


class ValidateQuestionResponse(BaseModel):
    valid: bool
    message: str | None = None


class TarotShareCard(BaseModel):
    position_name: str = ""
    name: str = ""
    meaning: str = ""
    image: str = ""
    is_reversed: bool | None = None


class TarotShareRequest(BaseModel):
    init_data: str = ""
    question: str = ""
    overall: str = ""
    spread_id: str = ""
    cards: list[TarotShareCard] = []
    chat_transcript: str = ""
    practical_advice: str = ""


class TarotShareResponse(BaseModel):
    ok: bool
    message: str = ""


class TarotSharePrepareResponse(BaseModel):
    ok: bool
    token: str = ""
    message: str = ""


def _looks_like_gibberish(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 4:
        return True
    has_space = " " in t
    has_punct = any(c in t for c in ".?!,…-")
    letters = sum(1 for c in t if c.isalpha())
    if not has_space and not has_punct and letters >= 3 and len(t) < 25:
        return True
    if not has_space and len(t) < 15:
        return True
    return False


def _load_tarot_descriptions() -> dict:
    try:
        data_path = Path(__file__).resolve().parent.parent / "data" / "tarot_card_descriptions.json"
        if data_path.exists():
            return json.loads(data_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _norm_url(url: str, base: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if not base:
        return ""
    return f"{base.rstrip('/')}/{u.lstrip('/')}"


def _build_share_footer(full_text_fits: bool) -> str:
    astrov_link = f'<a href="{BOT_LINK}">TARO</a>'
    if full_text_fits:
        return f"Сделай свой расклад тут 👉 {astrov_link}"
    return f"Ответы на свои вопросы ищи тут 👉 {astrov_link}"


def _build_photo_caption_html(payload: TarotShareRequest) -> str:
    spread_name = SPREAD_NAMES_RU.get(payload.spread_id or "single", "Расклад")
    astrov_link = f'<a href="{BOT_LINK}">TARO</a>'
    lines = [
        f"🔮 Расклад «{spread_name}» от {astrov_link}",
        "",
        "Полный текст расклада, диалог и толкования карт: см. прикреплённый файл .txt.",
    ]
    return "\n".join(lines) + "\n\n" + _build_share_footer(full_text_fits=True)


def _build_single_card_day_caption_html(payload: TarotShareRequest) -> str:
    from html import escape as html_esc

    spread_name = SPREAD_NAMES_RU.get(payload.spread_id or "single", "Карта дня")
    astrov_link = f'<a href="{BOT_LINK}">TARO</a>'
    lines: list[str] = [f"🔮 Расклад «{spread_name}» от {astrov_link}", ""]
    q = (payload.question or "").strip()
    if q:
        lines.extend([f"❓ {html_esc(q)}", ""])
    ct = (payload.chat_transcript or "").strip()
    if ct:
        lines.extend(["💬 Диалог с тарологом", "", html_esc(ct), ""])
    for i, c in enumerate((payload.cards or [])[:1], start=1):
        pos = html_esc((c.position_name or "").strip() or f"Позиция {i}")
        name = html_esc((c.name or "").strip() or "Карта")
        meaning = (c.meaning or "").strip()
        rev = c.is_reversed
        orient = " (перевёрнутая)" if rev is True else (" (прямая)" if rev is False else "")
        lines.append(f"{i}. {pos}: {name}{orient}")
        if meaning:
            lines.extend(["", html_esc(meaning)])
    adv = (payload.practical_advice or "").strip()
    if adv:
        lines.extend(["", "✨ Пожелание", html_esc(adv)])
    lines.extend(["", _build_share_footer(full_text_fits=True)])
    return "\n".join(lines)


def _build_tarot_full_text_file(payload: TarotShareRequest) -> str:
    spread_name = SPREAD_NAMES_RU.get(payload.spread_id or "single", "Расклад")
    lines: list[str] = [f"TARO — расклад «{spread_name}»", f"Приложение: {BOT_LINK}", ""]
    q = (payload.question or "").strip()
    if q:
        lines.extend(["--- Вопрос ---", q, ""])
    ct = (payload.chat_transcript or "").strip()
    if ct:
        lines.extend(["--- Диалог с тарологом ---", ct, ""])
    lines.append("--- Карты ---")
    for i, c in enumerate(payload.cards, start=1):
        pos = (c.position_name or "").strip() or f"Позиция {i}"
        name = (c.name or "").strip() or "Карта"
        meaning = (c.meaning or "").strip()
        rev = c.is_reversed
        orient = " (перевёрнутая)" if rev is True else (" (прямая)" if rev is False else "")
        lines.append(f"{i}. {pos}: {name}{orient}")
        if meaning:
            lines.append(meaning)
        lines.append("")
    ov = (payload.overall or "").strip()
    if ov:
        lines.extend(["--- Итог расклада ---", ov, ""])
    adv = (payload.practical_advice or "").strip()
    if adv:
        lines.extend(["--- Совет ---", adv, ""])
    return "\n".join(lines).rstrip() + "\n"


@router.post("/tarot/validate-question", response_model=ValidateQuestionResponse)
async def tarot_validate_question(payload: ValidateQuestionRequest) -> ValidateQuestionResponse:
    q = (payload.question or "").strip()
    if not q:
        return ValidateQuestionResponse(valid=True, message=None)
    if _looks_like_gibberish(q):
        return ValidateQuestionResponse(
            valid=False,
            message="Пожалуйста, задайте осмысленный вопрос словами (например: «Что меня ждёт в работе?»).",
        )
    return ValidateQuestionResponse(valid=True, message=None)


@router.post("/tarot/draw", response_model=TarotResponse)
async def tarot_draw(payload: TarotRequest, db: AsyncSession = Depends(get_db)) -> TarotResponse:
    telegram_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    await check_limits(db, telegram_id, "tarot", usage_key="single")

    gender_hint = gender_hint_for_prompt(None, None)
    card_name = payload.card_name or random.choice(ARCANA)
    position_display = (payload.position_name or "").strip()
    if not position_display and payload.position is not None and payload.total is not None:
        idx0 = resolve_spread_position_index(payload.position, int(payload.total))
        position_display = get_position_name(idx0, int(payload.total))
    elif not position_display:
        position_display = "общая позиция"

    visual_description = "отсутствует"
    card_id = (payload.card_id or "").strip().replace(".jpg", "").replace(".jpeg", "").replace(".png", "")
    if card_id:
        descriptions = _load_tarot_descriptions()
        deck = (payload.deck or "").strip()
        visual = _find_visual_description(descriptions, deck, card_id, payload.card_name or "")
        if visual and visual.strip():
            visual_description = visual.strip()

    is_overall = (card_name or "").lower().strip() == "общий расклад"
    system = TAROT_SINGLE_CARD_SYSTEM + f" {gender_hint} "
    if is_overall:
        system = (
            "Ты профессиональный таролог: говоришь точно, по делу и без украшательств. "
            f"{gender_hint} "
            "Отвечай только на русском, без списков, без * и #."
        )
        prompt = (
            f"Итог расклада. Вопрос: {payload.question or 'общая тема'}. "
            "Синтезируй все выпавшие карты в единую историю. 8-10 предложений."
        )
    else:
        card_type = get_tarot_card_type(card_name or "", card_id or None)
        prompt = build_tarot_single_card_user_prompt(
            card_name=card_name or "карта",
            card_type=card_type,
            position_name=position_display,
            question=payload.question or "общая тема",
            visual_description=visual_description,
            is_reversed=bool(payload.is_reversed),
        )

    try:
        max_tok = 560 if is_overall else 320
        interpretation = await ai_client.generate_text(
            prompt,
            system_prompt=system,
            max_tokens=max_tok,
            user_id=telegram_id,
            profile_id=None,
            feature_type="tarot_legacy",
        )
    except Exception as exc:
        logger.exception("Tarot draw AI failed: %s", exc)
        interpretation = "Звезды молчат. Попробуйте позже."
    interpretation = interpretation or "Звезды молчат. Попробуйте позже."

    await increment_daily(db, telegram_id, "tarot")
    db.add(
        History(
            user_id=telegram_id,
            type=HistoryType.TAROT,
            request_content=(payload.question or "")[:2000] or None,
            response_content=interpretation[:5000],
        )
    )
    await db.commit()
    return TarotResponse(card_name=card_name, interpretation=interpretation)


@router.post("/tarot/share/prepare", response_model=TarotSharePrepareResponse)
async def tarot_share_prepare(payload: TarotShareRequest) -> TarotSharePrepareResponse:
    if not get_settings().TELEGRAM_BOT_TOKEN:
        return TarotSharePrepareResponse(ok=False, message="Бот не настроен.")
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        return TarotSharePrepareResponse(ok=False, message="Откройте приложение из Telegram.")
    settings = get_settings()
    base_url = (settings.APP_URL or "").rstrip("/")
    app_url = f"{base_url}/tarot" if base_url and not base_url.endswith("/tarot") else (base_url or "")
    urls = [_norm_url(c.image, base_url) for c in payload.cards if (c.image or "").strip()]
    first_url = urls[0] if urls else None
    caption = (
        _build_single_card_day_caption_html(payload)
        if (payload.spread_id or "").strip() == "single"
        else _build_photo_caption_html(payload)
    )
    token = str(uuid.uuid4())
    await cache_set_json(
        f"tarot_share:{token}",
        {"first_url": first_url or "", "caption": caption, "app_url": app_url},
        ttl_seconds=300,
    )
    return TarotSharePrepareResponse(ok=True, token=token)


@router.post("/tarot/share", response_model=TarotShareResponse)
async def tarot_share(payload: TarotShareRequest) -> TarotShareResponse:
    if not get_settings().TELEGRAM_BOT_TOKEN:
        return TarotShareResponse(ok=False, message="Бот не настроен.")
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        return TarotShareResponse(ok=False, message="Откройте приложение из Telegram.")
    try:
        from aiogram.types import BufferedInputFile, InputMediaPhoto
        from app.bot.main import get_bot

        bot = get_bot()
        settings = get_settings()
        base_url = (settings.APP_URL or "").rstrip("/")
        urls = [_norm_url(c.image, base_url) for c in payload.cards if (c.image or "").strip()]
        urls = [u for u in urls if u.startswith("http")]
        is_card_of_day = (payload.spread_id or "").strip() == "single"
        photo_caption = _build_single_card_day_caption_html(payload) if is_card_of_day else _build_photo_caption_html(payload)
        caption_limit = 1024
        footer_truncated = _build_share_footer(full_text_fits=False)
        if len(photo_caption) > caption_limit:
            reserve = len("\n\n") + len(footer_truncated)
            max_content = max(0, caption_limit - reserve)
            photo_caption = (
                (photo_caption[: max_content - 3].rsplit("\n", 1)[0] or photo_caption[: max_content - 3]) + "..."
                if max_content > 20
                else photo_caption[:caption_limit]
            )
            photo_caption = photo_caption + "\n\n" + footer_truncated

        if len(urls) >= 2:
            media = [InputMediaPhoto(media=urls[0], caption=photo_caption, parse_mode="HTML"), *[InputMediaPhoto(media=u) for u in urls[1:10]]]
            await bot.send_media_group(user_id, media=media)
        elif urls:
            await bot.send_photo(user_id, photo=urls[0], caption=photo_caption, parse_mode="HTML")
        else:
            await bot.send_message(user_id, photo_caption, parse_mode="HTML")

        if not is_card_of_day:
            full_txt = _build_tarot_full_text_file(payload)
            doc = BufferedInputFile(full_txt.encode("utf-8"), filename="taro_tarot_rasklad.txt")
            await bot.send_document(user_id, document=doc, caption="Полный текст расклада.")
        return TarotShareResponse(ok=True, message="Расклад отправлен в личные сообщения бота.")
    except Exception as e:
        return TarotShareResponse(ok=False, message=f"Не удалось отправить: {e!s}")
