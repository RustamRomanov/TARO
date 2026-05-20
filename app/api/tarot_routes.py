from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import random
import re
import socket
import time
from hashlib import sha1
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import get_telegram_user_id_from_init_data, sanitize_profile_id_for_db
from app.db.models import TarotReading, User
from app.db.session import get_db
from app.services.ai_client import AIServiceClient
from app.services.cache import (
    acquire_lock as cache_acquire_lock,
    get_json as cache_get_json,
    release_lock as cache_release_lock,
    set_json as cache_set_json,
)
from app.services.limits import (
    check_limits,
    deduct_balance,
    has_paid_access,
    has_welcome_free_access,
    increment_daily,
    tarot_single_like_usage_today,
)
from app.services.personalization import age_style_instruction
from app.services.tarot_knowledge import get_tarot_expert_system_prefix
from app.services.prompts.tarot_rw import (
    TAROT_BATCH_PER_CARD_INTERPRETATION_RULES,
    TAROT_SUMMARY_OVERALL_RULES,
    get_tarot_card_type,
)
from app.services.runtime_metrics import incr_counter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tarot", tags=["tarot"])
ai_client = AIServiceClient()
_TAROT_DESCRIPTIONS_CACHE: dict[str, Any] | None = None
_TAROT_DECK_NORM_CACHE: dict[str, dict[str, str]] = {}
_DRAW_BATCH_USER_LOCKS: dict[int, asyncio.Lock] = {}
_DRAW_BATCH_USER_LOCKS_GUARD = asyncio.Lock()
_VISION_CB_LOCK = asyncio.Lock()
_VISION_CB_OPEN_UNTIL_MONO = 0.0
_VISION_CB_CONSECUTIVE_FAILS = 0
_VISION_CB_FAIL_THRESHOLD = 4
_VISION_CB_COOLDOWN_SEC = 45.0


def _tarot_interpretation_model_override() -> str | None:
    """Модель для толкования расклада (draw-batch, доработка). Пусто: как у основного текста (AI_TEXT_MODEL)."""
    m = (getattr(get_settings(), "AI_TAROT_INTERPRETATION_MODEL", None) or "").strip()
    return m or None


def _chat_cache_key(user_id: int, reading_id: str) -> str:
    return f"tarot:chat_fallback:{user_id}:{reading_id}"


async def _get_draw_batch_user_lock(user_id: int) -> asyncio.Lock:
    """
    In-process serialization for draw-batch per user to reduce race windows.
    DB row lock still protects cross-process cases on databases that support it.
    """
    async with _DRAW_BATCH_USER_LOCKS_GUARD:
        lock = _DRAW_BATCH_USER_LOCKS.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _DRAW_BATCH_USER_LOCKS[user_id] = lock
        return lock


def _tarot_chat_rate_key(user_id: int, channel: str) -> str:
    return f"tarot:chat_rate:{channel}:{user_id}"


async def _enforce_tarot_chat_rate_limit(user_id: int, channel: str, limit: int, window_sec: int) -> None:
    """
    Soft rate-limit for expensive chat endpoints.
    Uses cache window counter; best-effort in-memory/redis implementation.
    """
    key = _tarot_chat_rate_key(user_id, channel)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    state = await cache_get_json(key)
    if not isinstance(state, dict):
        state = {"count": 0, "start": now_ts}
    start = int(state.get("start") or now_ts)
    count = int(state.get("count") or 0)
    if now_ts - start >= window_sec:
        start = now_ts
        count = 0
    count += 1
    await cache_set_json(key, {"count": count, "start": start}, ttl_seconds=window_sec)
    if count > limit:
        raise HTTPException(status_code=429, detail="Слишком много запросов. Попробуйте чуть позже.")


SPREADS: dict[str, dict[str, Any]] = {
    "single": {"name": "1 карта Совет", "deep": False},
    "three_cards": {"name": "3 карты", "deep": False},
    "financial": {"name": "5 карт Финансовый", "deep": False},
    "six_cards": {"name": "6 карт Отношения", "deep": True},
    "ten_cards": {"name": "10 карт Кельтский крест", "deep": True},
}

SPREAD_ANALYSIS_RULES: dict[str, str] = {
    "single": (
        "Одна карта на день: пользователь уже видит картинку, не пересказывай подряд, что на иллюстрации. "
        "Опирайся на описание изображения карты и на вопрос: вплетай символы, стихии, жесты и детали (огонь, вода, фигуры и т.п.) в смысл для дня. "
        "Позиция по смыслу «сегодня», не называй её просто «карта». Без канцелярита и без шаблона «зафиксируй шаг». "
        "Если передано описание изображения, не подставляй классическую сцену Rider-Waite или другой стандартной колоды: опирайся только на переданное описание (если там птицы и небо, не пиши про человека на башне и т.п.). "
        "Не используй длинное тире в тексте для пользователя."
    ),
    "three_cards": (
        "Три позиции: прошлое, настоящее, будущее. В каждой карте опирайся на описание изображения и вопрос: связывай символику с позицией, без пересказа картинки в начале. "
        "Не используй шаблон «карта в позиции …». Итог: одна цельная история. Не повторяй одни и те же фразы в конце блоков. "
        "Не используй длинное тире в тексте для пользователя."
    ),
    "financial": (
        "Финансовая лестница (5): 1=текущая ситуация, 2=ресурсы, 3=возможности, 4=действия, 5=результат. "
        "Покажи динамику роста, препятствия и точки усиления. "
        "План по деньгам: опирайся на выпавшие карты и вопрос; формат на твоё усмотрение: один шаг, несколько шагов или короткий план; избегай шаблонных фраз и не повторяй одни и те же формулировки в разных раскладах. "
        "Не пересказывай картинку подряд; символы на картах вплетай в смысл. Не используй длинное тире в тексте для пользователя."
    ),
    "six_cards": (
        "Отношения (6): 1 и 2 - чувства пары (Она и Он; сравни напрямую), "
        "3 - текущее взаимодействие, 4 - объединяющее, 5 - разъединяющее, 6 - итог: куда это складывается. "
        "Обязательно укажи, где гармония, где конфликт, и как карта 6 подводит черту. Простой язык. "
        "Не пересказывай картинки подряд; символы вплетай в смысл. Не используй длинное тире в тексте для пользователя."
    ),
    "ten_cards": (
        "Кельтский крест (10 карт). Порядок считывания по традиции: сначала крест (карты 1-4), затем посох (5-6), затем колонка (7-10). "
        "1=суть ситуации (центр), 2=препятствие/вызов (поперечная), 3=над центром (цель, куда смотреть), 4=под центром (основание/корень), "
        "5=слева (прошлое), 6=справа (ближайшее будущее), 7=вы в ситуации, 8=окружение, 9=надежды и страхи, 10=итог. "
        "Структура ответа: краткое резюме (1-2 предложения), разбор карт 1-4 (крест), затем 5-6 (временная ось), затем 7-10 (колонка и итог), итоговый совет. "
        "Не пересказывай картинки подряд; символы вплетай в смысл. Не используй длинное тире в тексте для пользователя."
    ),
}

SINGLE_POOL = [
    "The Fool",
    "The Magician",
    "The High Priestess",
    "The Empress",
    "The Emperor",
    "The Hierophant",
    "The Lovers",
    "The Chariot",
    "Strength",
    "The Hermit",
    "Wheel of Fortune",
    "Justice",
    "The Hanged Man",
    "Death",
    "Temperance",
    "The Devil",
    "The Tower",
    "The Star",
    "The Moon",
    "The Sun",
    "Judgement",
    "The World",
]


class BatchCard(BaseModel):
    card_id: str
    position: int
    position_name: str
    is_reversed: bool = False
    card_name: str = ""
    image: str = ""


class DrawBatchRequest(BaseModel):
    init_data: str = ""
    profile_id: int | None = None
    personalize: bool = False
    spread_code: str = "three_cards"
    question: str = ""
    cards: list[BatchCard] = Field(default_factory=list)
    allow_reversed: bool = True
    deck: str = "classic"
    deck_card_ids: list[str] = Field(default_factory=list)
    deck_card_names: dict[str, str] = Field(default_factory=dict)


class CardInterpretation(BaseModel):
    position: int
    position_name: str
    interpretation: str
    card_id: str
    card_name: str
    is_reversed: bool


class DrawBatchResponse(BaseModel):
    reading_id: str
    cards: list[dict[str, Any]]
    cards_interpretations: list[CardInterpretation]
    summary: str
    overall: str = ""
    question_essence: str
    follow_up_questions: list[str]
    advice: str
    chat_id: str


class TarotChatRequest(BaseModel):
    init_data: str = ""
    reading_id: str
    message: str


class TarotChatResponse(BaseModel):
    reading_id: str
    response: str
    updated_advice: str
    new_questions: list[str]
    chat_history: list[dict[str, str]]


class TarotTarologistChatRequest(BaseModel):
    init_data: str = ""
    spread_id: str = ""
    deck_id: str = ""
    deck_name: str = ""
    spread_name: str = ""
    messages: list[dict[str, str]] = []
    message: str = ""


class TarotTarologistChatResponse(BaseModel):
    response: str
    enough_info: bool = False
    suggested_question: str = ""
    refuse_to_continue: bool = False


class TarotHistoryItem(BaseModel):
    id: str
    spread_code: str
    question: str
    summary: str
    cards_preview: list[dict[str, Any]]
    created_at: datetime


class TarotHistoryResponse(BaseModel):
    items: list[TarotHistoryItem]
    total: int
    page: int
    limit: int


class TarotStatsResponse(BaseModel):
    total_readings: int
    top_cards: list[dict[str, Any]]
    reversed_ratio: dict[str, int]
    arcana_ratio: dict[str, int]
    recurring_cards: list[dict[str, Any]]


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    for candidate in (
        text,
        text.replace("```json", "").replace("```", "").strip(),
    ):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            try:
                data = json.loads(text[start:end].strip())
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


def _safe_text(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _strip_technical_card_tokens(text: str) -> str:
    src = str(text or "")
    if not src:
        return ""
    out = re.sub(r"[«\"']?[A-Za-z0-9_-]{2,}\.(?:jpg|jpeg|png|webp)[»\"']?", "карта дня", src, flags=re.I)
    out = re.sub(r"\b(?:wands|cups|swords|pentacles|disks)\d+\b", "карта дня", out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip()


def _ensure_terminal_punctuation(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""
    return src if re.search(r"[.!?…]$", src) else f"{src}."


def _reversed_card_label(card_label: str) -> str:
    label = (card_label or "карта").strip()
    low = label.lower()
    plural_tokens = ("влюбл",)
    neuter_tokens = ("солнц", "колесо")
    masculine_tokens = (
        "шут",
        "маг",
        "император",
        "иерофант",
        "отшельник",
        "повеш",
        "дьявол",
        "суд",
        "мир",
        "туз",
        "паж",
        "рыцарь",
        "король",
    )
    if any(token in low for token in plural_tokens):
        prefix = "Перевернутые"
    elif any(token in low for token in neuter_tokens):
        prefix = "Перевернутое"
    elif any(token in low for token in masculine_tokens):
        prefix = "Перевернутый"
    else:
        prefix = "Перевернутая"
    return f"{prefix} {label}"


def _single_card_human_label(card: dict[str, Any] | None) -> str:
    if not isinstance(card, dict):
        return "эта карта"
    label = _card_display_label(
        str(card.get("card_name") or ""),
        str(card.get("card_id") or ""),
    )
    if label:
        return label
    raw_id = re.sub(r"\.(jpg|jpeg|png|webp)$", "", str(card.get("card_id") or ""), flags=re.I).strip()
    suit_match = re.match(r"^(wands|cups|swords|pentacles|disks|coins)[_-]?(\d{1,2})$", raw_id, flags=re.I)
    if suit_match:
        suit_raw = suit_match.group(1).lower()
        rank_n = int(suit_match.group(2))
        suit_ru_map = {
            "wands": "Жезлов",
            "cups": "Кубков",
            "swords": "Мечей",
            "pentacles": "Пентаклей",
            "disks": "Пентаклей",
            "coins": "Пентаклей",
        }
        rank_ru = {
            1: "Туз",
            2: "Двойка",
            3: "Тройка",
            4: "Четвёрка",
            5: "Пятёрка",
            6: "Шестёрка",
            7: "Семёрка",
            8: "Восьмёрка",
            9: "Девятка",
            10: "Десятка",
            11: "Паж",
            12: "Рыцарь",
            13: "Королева",
            14: "Король",
        }.get(rank_n)
        suit_ru = suit_ru_map.get(suit_raw, "")
        if rank_ru and suit_ru:
            return f"{rank_ru} {suit_ru}"
    idx = _card_index_from_id(str(card.get("card_id") or ""))
    if idx is not None:
        std = _standard_card_name_ru(idx).strip()
        if std:
            return std
    return "эта карта"


def _single_fast_fallback_interpretation(
    *,
    card_label: str,
    card_type: str,
    is_reversed: bool,
) -> str:
    label = (card_label or "Эта карта").strip()
    ctype = (card_type or "").strip().lower()
    low = label.lower()

    major_hints = {
        "шут": (
            "день про новый опыт и свободу. Пробуй легче, но не прыгай туда, где нет опоры",
            "новизна может тянуть в хаос. Сначала проверь риск, потом соглашайся на приключение",
        ),
        "маг": (
            "день про личную волю. Скажи прямо, чего хочешь, и сделай первый управляемый шаг",
            "воля распыляется или уходит в контроль. Не обещай больше, чем можешь сделать руками",
        ),
        "жрица": (
            "день про тишину и интуицию. Не торопи ответ, лучше прислушайся к тому, что уже чувствуешь",
            "интуицию может перекрывать тревога. Не додумывай за других, дождись фактов",
        ),
        "императрица": (
            "день про живой ресурс, тело и заботу. Поддержи то, что растёт, вместо сухого контроля",
            "ресурс утекает через усталость или лишнюю заботу о других. Верни внимание к себе и телу",
        ),
        "император": (
            "день про порядок и границы. Решение лучше принять спокойно, с опорой на правила",
            "контроль может стать жёстким. Ослабь хватку там, где порядок уже превратился в давление",
        ),
        "иерофант": (
            "день про ценности, правила и честный совет. Выбери принцип, которому правда доверяешь",
            "чужие правила могут давить сильнее внутренней правды. Сверь совет с собой, а не только с авторитетом",
        ),
        "влюбл": (
            "день про выбор сердцем. Важно честно назвать, к чему тебя тянет, и не играть в безразличие",
            "выбор может зависнуть из-за сомнений или зависимости от чужой реакции. Не обещай из страха потерять контакт",
        ),
        "колесниц": (
            "день про движение и управление курсом. Выбери направление и держи его без резких поворотов",
            "движение может буксовать из-за борьбы двух желаний. Сначала собери себя, потом жми на газ",
        ),
        "сила": (
            "день про мягкую силу. Удержи импульс спокойно, без борьбы за власть",
            "эмоция может взять верх. Не дави и не доказывай, лучше верни себе спокойный тон",
        ),
        "отшельник": (
            "день про тишину и личный ответ. Меньше внешнего шума, больше честного разговора с собой",
            "одиночество может стать уходом от жизни. Не закрывайся полностью, оставь один ясный контакт с реальностью",
        ),
        "колесо": (
            "день про поворот обстоятельств. Заметь шанс и не держись за сценарий, который уже меняется",
            "перемены могут казаться случайными и раздражать. Не пытайся контролировать всё сразу, выбери ближайшую точку влияния",
        ),
        "справедлив": (
            "день про честность и последствия. Смотри на факты, договорённости и свою часть ответственности",
            "оценка может быть перекошенной. Не суди себя или других по одной эмоции, проверь факты",
        ),
        "повеш": (
            "день про паузу и другой взгляд. То, что не двигается, просит сменить угол зрения",
            "пауза может стать зависанием. Не жертвуй собой там, где нужен честный отказ",
        ),
        "смерт": (
            "день про завершение старой формы. Отпусти то, что уже не оживает, и освободи место дальше",
            "перемены могут пугать, поэтому рука тянется удержать старое. Не тащи за собой то, что уже закончилось",
        ),
        "умерен": (
            "день про меру и восстановление баланса. Смешивай противоположности мягко, без крайностей",
            "баланс нарушен: то слишком много, то слишком мало. Верни умеренный темп и не лечи хаос новым хаосом",
        ),
        "дьявол": (
            "день про привязку, соблазн или зависимость. Назови, что забирает свободу, и не корми это вниманием",
            "искушение может маскироваться под необходимость. Проверь, где ты говоришь «надо», хотя на самом деле завис",
        ),
        "башн": (
            "день про правду, которая ломает слабую конструкцию. Лучше увидеть трещину сейчас, чем чинить обман позже",
            "страх перемен может заставить держаться за ненадёжное. Не укрепляй то, что давно просит перестройки",
        ),
        "звезд": (
            "день про надежду и дальний ориентир. Делай маленький шаг к тому, что возвращает веру",
            "надежда может казаться далёкой. Не требуй мгновенного результата, сохрани направление",
        ),
        "лун": (
            "день про неясность и тревожные мысли. Не верь первой догадке, сначала проверь факты",
            "мысли могут быть затуманены. Не принимай важное решение, пока не проверишь факты",
        ),
        "солнц": (
            "день про ясность и простую радость. Покажи себя прямо и не усложняй там, где всё уже видно",
            "ясность может прятаться за усталостью или стеснением. Не гаси свой свет из-за чужого настроения",
        ),
        "суд": (
            "день про пробуждение и важный вывод. Признай правду, которую давно откладывал",
            "зов к переменам может пугать. Не возвращайся к старой роли только потому, что она привычна",
        ),
        "мир": (
            "день про завершение цикла. Собери результат и признай, что этап уже стал цельным",
            "завершение может затягиваться из-за мелких хвостов. Закрой главное, а не полируй бесконечно детали",
        ),
    }
    suit_hints = {
        "жезл": ("дело просит живого действия", "можно сорваться в спешку или раздражение"),
        "wand": ("дело просит живого действия", "можно сорваться в спешку или раздражение"),
        "куб": ("чувство просит честного проявления", "ожидания могут запутать реальное чувство"),
        "cup": ("чувство просит честного проявления", "ожидания могут запутать реальное чувство"),
        "меч": ("разговор или решение просит ясных слов", "мысли могут стать резкими или тревожными"),
        "sword": ("разговор или решение просит ясных слов", "мысли могут стать резкими или тревожными"),
        "пентак": ("быт, деньги или тело просят конкретного действия", "быт, деньги или тело могут стать источником напряжения"),
        "диск": ("быт, деньги или тело просят конкретного действия", "быт, деньги или тело могут стать источником напряжения"),
        "монет": ("быт, деньги или тело просят конкретного действия", "быт, деньги или тело могут стать источником напряжения"),
    }
    suit_contexts = {
        "жезл": (
            "В обычном дне это может быть работа, спорт или желание быстро что-то доказать.",
            "Если внутри много злости или спешки, лучше дать телу движение, а не срываться на близких.",
        ),
        "wand": (
            "В обычном дне это может быть работа, спорт или желание быстро что-то доказать.",
            "Если внутри много злости или спешки, лучше дать телу движение, а не срываться на близких.",
        ),
        "куб": (
            "В обычном дне это может быть любовь, дружба, забота или обида на близкого человека.",
            "Чувства могут путать. Не проверяй любовь молчанием или претензиями, лучше скажи проще, что тебе нужно.",
        ),
        "cup": (
            "В обычном дне это может быть любовь, дружба, забота или обида на близкого человека.",
            "Чувства могут путать. Не проверяй любовь молчанием или претензиями, лучше скажи проще, что тебе нужно.",
        ),
        "меч": (
            "В обычном дне это может быть ссора, резкое сообщение или неприятный разговор.",
            "Не делай вывод на злости. Сначала проверь факты, потом говори прямо и коротко.",
        ),
        "sword": (
            "В обычном дне это может быть ссора, резкое сообщение или неприятный разговор.",
            "Не делай вывод на злости. Сначала проверь факты, потом говори прямо и коротко.",
        ),
        "пентак": (
            "В обычном дне это может быть работа, здоровье, покупка, долг или разговор о деньгах.",
            "Не смешивай тревогу о деньгах с реальными цифрами. Посмотри, что нужно оплатить или спокойно обсудить.",
        ),
        "диск": (
            "В обычном дне это может быть работа, здоровье, покупка, долг или разговор о деньгах.",
            "Не смешивай тревогу о деньгах с реальными цифрами. Посмотри, что нужно оплатить или спокойно обсудить.",
        ),
        "монет": (
            "В обычном дне это может быть работа, здоровье, покупка, долг или разговор о деньгах.",
            "Не смешивай тревогу о деньгах с реальными цифрами. Посмотри, что нужно оплатить или спокойно обсудить.",
        ),
    }
    major_contexts = {
        "шут": "В обычном дне это может быть знакомство, поездка или спонтанное решение.",
        "маг": "В обычном дне это разговор, заявка, работа или момент, где нужно самому начать.",
        "жрица": "В обычном дне это недосказанность, тайна или чувство, что тебе говорят не всё.",
        "императрица": "В обычном дне это забота о теле, доме, любви или здоровье.",
        "император": "В обычном дне это правила, начальник, документы или разговор о границах.",
        "иерофант": "В обычном дне это семья, брак, учёба, совет старшего или обещание.",
        "влюбл": "В обычном дне это любовь, симпатия, дружба или честный выбор в отношениях.",
        "колесниц": "В обычном дне это поездка, работа, спорт или желание доказать, что ты справишься.",
        "сила": "В обычном дне это злость, страсть, спорт или желание защитить своё.",
        "отшельник": "В обычном дне это отдых, здоровье, пауза в общении или желание побыть одному.",
        "колесо": "В обычном дне это звонок, встреча, деньги или событие, которое быстро меняет планы.",
        "справедлив": "В обычном дне это документы, долги, договор, кредит или обещание.",
        "повеш": "В обычном дне это задержка, усталость, подвешенная работа или ожидание чужого ответа.",
        "смерт": "В обычном дне это расставание со старой привычкой, работой или решением, которое уже отжило.",
        "умерен": "В обычном дне это здоровье, режим, отдых или спокойный разговор после ссоры.",
        "дьявол": "В обычном дне это ревность, жадность, кредит, обман или токсичная привязка.",
        "башн": "В обычном дне это ссора, вскрытый обман, внезапная новость или резкая смена плана.",
        "звезд": "В обычном дне это дружба, поддержка, здоровье или мечта, к которой хочется вернуться.",
        "лун": "В обычном дне это тревога, слухи, недоверие или ситуация, где лучше не верить первому впечатлению.",
        "солнц": "В обычном дне это радость, любовь, дети, отдых или честный разговор.",
        "суд": "В обычном дне это старая тема, семейный вопрос, долг, признание или шанс исправить ошибку.",
        "мир": "В обычном дне это итог, поездка, переезд, закрытие долга или окончание проекта.",
    }
    rank_hints = {
        "туз": "начни с малого импульса и не перегружай старт ожиданиями",
        "двойка": "сравни два варианта и выбери один, иначе день уйдёт в зависание",
        "тройка": "проверь первые результаты и договорись с теми, кто влияет на дело",
        "четвёрка": "увидь, где стабильность помогает, а где уже мешает двигаться",
        "пятёрка": "не раздувай борьбу, сначала пойми, за что именно споришь",
        "шестёрка": "верни доверие, память или спокойный обмен, где связь была нарушена",
        "семёрка": "выбери реальный вариант из нескольких и не распыляйся на фантазии",
        "восьмёрка": "убери лишнее, чтобы процесс пошёл быстрее и проще",
        "девятка": "заметь накопленное напряжение и не делай вид, что ресурса бесконечно много",
        "десятка": "дойди до финальной точки и сними с себя лишнюю ношу",
        "паж": "смотри глазами ученика: важный знак придёт через деталь или вопрос",
        "рыцарь": "направь сильный импульс в один поступок, а не в резкий рывок",
        "королева": "управляй состоянием и средой вокруг себя зрелее, чем требуют обстоятельства",
        "король": "возьми ответственность за решение и за тон, которым оно будет сказано",
    }
    exact_hints = {
        ("двойка", "жезл"): (
            "это карта горизонта и планирования: хочется большего, но день просит выбрать маршрут, а не стоять у окна возможностей",
            "планы могут зависнуть между двумя направлениями. Не расширяй список вариантов, сначала выбери один реальный маршрут",
        ),
        ("десятка", "меч"): (
            "это карта болезненного завершения: сегодня важно признать, что старый способ думать себя исчерпал",
            "старый страх может снова давить на голову. Не возвращайся в мысль, которая уже показала свою цену",
        ),
        ("девятка", "меч"): (
            "это карта тревожных мыслей: не верь каждому страху, сначала отдели факт от ночного сценария",
            "тревога может казаться доказательством, хотя это только перегретая мысль. Проверь реальность через один спокойный факт",
        ),
        ("семёрка", "куб"): (
            "это карта вариантов и фантазий: сегодня легко захотеть всё сразу, поэтому отдели реальное желание от красивой иллюзии",
            "иллюзии могут сбивать выбор. Не гонись за самой красивой картинкой, выбери то, что можно проверить делом",
        ),
        ("семерка", "куб"): (
            "это карта вариантов и фантазий: сегодня легко захотеть всё сразу, поэтому отдели реальное желание от красивой иллюзии",
            "иллюзии могут сбивать выбор. Не гонись за самой красивой картинкой, выбери то, что можно проверить делом",
        ),
        ("туз", "куб"): (
            "это карта свежего чувства. День может открыть симпатию, вдохновение или мягкое примирение. Не прячь тепло, но и не требуй от него сразу обещаний",
            "чувство может переливаться через край. Сначала назови себе, что именно задело, и не превращай эмоцию в претензию",
        ),
        ("тройка", "жезл"): (
            "это карта ожидания первых результатов: ты уже сделал шаг, теперь смотри, что отвечает мир, и не бросай начатое на полпути",
            "результат может задерживаться. Не стой у горизонта пассивно, проверь один контакт, письмо или договорённость",
        ),
        ("десятка", "жезл"): (
            "это карта перегруза: ты несёшь слишком много задач сразу. Оставь главное, а лишнее перенеси или попроси помощи",
            "нагрузка стала тяжелее, чем кажется со стороны. Не доказывай выносливость, сними хотя бы одну обязанность сегодня",
        ),
        ("девятка", "пентак"): (
            "это карта личной самостоятельности: наведи красоту и порядок в своём пространстве, день поддержит спокойное удовольствие от результата",
            "удобство может превратиться в изоляцию или недовольство. Проверь, где ты закрываешься за привычкой всё делать самому",
        ),
        ("десятка", "пентак"): (
            "это карта дома, семьи и больших договорённостей. Сегодня полезно заняться тем, что укрепляет общий быт: платёж, документ, разговор о правилах",
            "семейные или денежные обязательства могут давить. Раздели, что действительно твоё, а что на тебя просто переложили",
        ),
        ("рыцарь", "пентак"): (
            "это карта медленного, надёжного шага. Не ускоряйся ради красивого эффекта, лучше спокойно доведи одно дело до результата",
            "дело может вязнуть из-за упрямства или усталости. Сдвинь его маленьким практичным шагом, без рывка и самокритики",
        ),
        ("королева", "пентак"): (
            "это карта зрелой заботы о теле, деньгах и быте: проверь ресурс, наведи порядок в одном конкретном деле и не тащи на себе чужую ответственность",
            "забота о ресурсах может превратиться в контроль или усталость. Сегодня важно вернуть себе опору: еда, тело, деньги, порядок в одном деле",
        ),
        ("король", "пентак"): (
            "это карта устойчивого хозяина положения. Проверь деньги, сроки и обещания, затем спокойно закрепи решение",
            "стремление всё удержать может сделать тебя жёстче нужного. Не меряй ценность дня только деньгами или контролем",
        ),
        ("четвёрка", "пентак"): (
            "это карта удержания и контроля: береги ресурс, но не сжимай всё так сильно, что перестаёт течь жизнь",
            "страх потерять ресурс может заставить держаться слишком крепко. Ослабь хватку там, где контроль уже не защищает",
        ),
        ("императрица", ""): (
            "это аркан живого ресурса: тело, дом, красота и забота сегодня важнее сухого контроля",
            "живой ресурс может быть истощён. Не требуй от себя плодородия там, где сначала нужны отдых и питание",
        ),
        ("отшельник", ""): (
            "это аркан внутреннего поиска: меньше внешнего шума, больше честного разговора с собой",
            "уединение может стать закрытостью. Останься с собой, но не отрезай единственный нужный контакт",
        ),
    }

    exact = ""
    for (rank_key, suit_key), hint in exact_hints.items():
        if rank_key in low and (not suit_key or suit_key in low):
            exact = hint[1] if is_reversed else hint[0]
            break

    major = next((hint for key, hint in major_hints.items() if key in low), None)
    major_context = next((hint for key, hint in major_contexts.items() if key in low), "")
    suit_key = next((key for key in suit_hints if key in low), "")
    suit = suit_hints.get(suit_key) if suit_key else None
    suit_context = ""
    if suit_key:
        ctx_pair = suit_contexts.get(suit_key)
        if ctx_pair:
            suit_context = ctx_pair[1 if is_reversed else 0]
    rank = next((hint for key, hint in rank_hints.items() if key in low), "")
    orientation_idx = 1 if is_reversed else 0

    if exact:
        core = exact
    elif ctype.startswith("major") or major is not None:
        core = (major or ("это аркан важного внутреннего урока", "урок карты может идти через задержку"))[orientation_idx]
    elif ctype.startswith("court"):
        core = f"эта карта показывает твой способ действовать сегодня. {rank or 'Выбери позицию осознанно'}"
    else:
        suit_text = (suit or ("повседневный выбор просит конкретики", "повседневный выбор может запутаться"))[orientation_idx]
        core = f"{suit_text}. {rank or 'Смотри на конкретный знак дня, а не на общий шум'}"

    display_label = _reversed_card_label(label) if is_reversed else label
    arcana_line = (
        "Это Старший аркан."
        if ctype.startswith("major") or major is not None
        else "Это Младший аркан."
    )
    context = major_context if ctype.startswith("major") or major is not None else suit_context
    if context:
        return f"{display_label}. {arcana_line} {core}. {context}"
    if is_reversed:
        return f"{display_label}. {arcana_line} {core}."
    return f"{display_label}. {arcana_line} {core}."


def _normalize_single_text_style(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""
    out = re.sub(r"\s+", " ", src)
    out = out.replace(";", ",")
    out = re.sub(r"(?i)\bкарта дня\s+на\s+сегодня\s*:\s*", "", out)
    out = re.sub(r"(?i)\bкарта дня\s*:\s*", "", out)
    out = out.replace(":", ".")
    out = re.sub(r"\.{2,}", ".", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", out) if p.strip()]
    fixed: list[str] = []
    for part in parts:
        first = part[0].upper() + part[1:] if part else part
        fixed.append(first)
    return _ensure_terminal_punctuation("\n".join(fixed))


def _compact_single_text(text: str, *, max_sentences: int = 4, max_chars: int = 430) -> str:
    src = str(text or "").strip()
    if not src:
        return ""
    normalized = _normalize_single_text_style(src)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", normalized.replace("\n", " ")) if p.strip()]
    if not parts:
        return normalized

    selected: list[str] = []
    total = 0
    for part in parts:
        next_total = total + len(part) + (1 if selected else 0)
        if selected and (len(selected) >= max_sentences or next_total > max_chars):
            break
        selected.append(part)
        total = next_total
        if len(selected) >= max_sentences:
            break

    compacted = "\n".join(selected or parts[:1]).strip()
    if len(compacted) > max_chars:
        compacted = compacted[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return _ensure_terminal_punctuation(compacted)


def _diversify_single_boilerplate(text: str, seed_key: str = "") -> str:
    src = str(text or "").strip()
    if not src:
        return ""
    variants = (
        "Сегодня фон дня такой",
        "На сегодня картина такая",
        "В этот день акцент такой",
        "По дню выходит так",
    )
    seed = sum(ord(ch) for ch in (seed_key or src))
    repl = variants[seed % len(variants)]
    out = re.sub(r"(?iu)\bситуация\s+складывается\s+так\b", repl, src)
    out = re.sub(r"(?iu)\bсегодня\s+важно\b", "Сейчас лучше", out)
    out = re.sub(r"(?iu)\bконтроль\s+над\s+ресурсами\b", "бережный режим", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _strip_direct_position_phrase(text: str) -> str:
    src = str(text or "")
    src = re.sub(r"(?i)\bв\s+прямом\s+положении\s+карта\s*", "", src)
    src = re.sub(r"(?i)\bпрямая\s+карта\s*", "", src)
    return re.sub(r"\s{2,}", " ", src).strip()


def _texts_too_similar(a: str, b: str) -> bool:
    """Проверка: расклад и совет не должны совпадать по тексту."""
    if not a or not b:
        return False
    a_norm = " ".join(re.split(r"\s+", a.lower().strip()))
    b_norm = " ".join(re.split(r"\s+", b.lower().strip()))
    if a_norm == b_norm:
        return True
    if len(a_norm) < 20 or len(b_norm) < 20:
        return False
    if a_norm in b_norm or b_norm in a_norm:
        return True
    wa = set(w for w in re.split(r"\W+", a_norm) if len(w) > 1)
    wb = set(w for w in re.split(r"\W+", b_norm) if len(w) > 1)
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / max(len(wa), len(wb))
    return overlap > 0.85


def _strip_three_cards_boilerplate(text: str) -> str:
    """Убирает шаблонные хвосты, которые дублируются между позициями и в общем итоге."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return t
    patterns = [
        r"Свяжите вывод этой позиции с вашим вопросом и выберите один ближайший шаг\.?",
        r"Сфокусируйтесь на одном практическом шаге, который можно сделать уже в ближайшие сутки\.?",
        r"Сконцентрируйтесь на конкретном действии в ближайшие сутки и перепроверьте вывод по фактам\.?",
    ]
    for p in patterns:
        t = re.sub(p, "", t, flags=re.IGNORECASE)
    ban_phrases = [
        r"зафиксировать\s+один\s+конкретный\s+шаг[^\.\!?]*[\.\!?]?",
        r"проверить\s+результат\s+по\s+фактам[^\.\!?]*[\.\!?]?",
        r"про\s+эту\s+линию\s+расклада[^\.\!?]*[\.\!?]?",
        r"в\s+практическом\s+плане[^\.\!?]*[\.\!?]?",
    ]
    for p in ban_phrases:
        t = re.sub(p, "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:")
    return t


def _strip_false_reversed_claims(text: str, is_reversed: bool) -> str:
    """Если карта прямая, убираем предложения про «перевёрнутую», чтобы не путать с рисунком."""
    if is_reversed or not (text or "").strip():
        return text or ""
    t = re.sub(r"[^.!?]*перевёрнут[^.!?]*[.!?]", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip(" ,.;:")


def _dedupe_similar_sentences(text: str) -> str:
    """Убирает дословные повторы предложений (типовой шаблон в итоге)."""
    raw = (text or "").strip()
    if not raw:
        return raw
    parts = re.split(r"(?<=[.!?])\s+", raw)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        norm = re.sub(r"\s+", " ", p.lower())
        if len(norm) > 35 and norm in seen:
            continue
        seen.add(norm)
        out.append(p)
    return " ".join(out)


def _sanitize_three_cards_interpretation(
    text: str,
    *,
    position_name: str,
    card_name: str,
    is_reversed: bool,
) -> str:
    """
    Убирает шаблоны и ложные «перевёрнут» для прямой карты.
    Раньше при словах прошлое/настоящее/будущее или длине >460 текст заменялся одной фразой: это ломало полноценные толкования.
    """
    src = re.sub(r"\s+", " ", (text or "").strip())
    if not src:
        return ""
    if len(src) > 4500:
        src = src[:4497].rstrip(" ,.;:") + "…"
    out = _strip_three_cards_boilerplate(src)
    if not is_reversed and "перевёрнут" in out.lower():
        out = re.sub(r"[^.!?]*перевёрнут[^.!?]*[.!?]", " ", out, flags=re.IGNORECASE)
        out = re.sub(r"\s+", " ", out).strip(" ,.;:")
    return out


def _question_is_third_person(question: str) -> bool:
    q = (question or "").lower()
    return bool(re.search(r"\b(друг|подруг|брата|сестр|муж|жен|партнер|партнёр|сын|дочь|он|она|ему|ей|его|ее|её)\b", q))


def _question_implies_no_current_partner(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    patterns = [
        r"\bвстречу\b.*\b(любов|партнер|партнёр)\b",
        r"\bкогда\b.*\bвстречу\b",
        r"\bпояв(ится|ится ли)\b.*\b(партнер|партнёр|любов)\b",
        r"\bбудет ли\b.*\b(отношени|партнер|партнёр)\b",
        r"\bнайду\b.*\b(любов|партнер|партнёр)\b",
        r"\bесть ли шанс\b.*\b(отношени|любов)\b",
    ]
    return any(re.search(p, q) for p in patterns)


def _text_assumes_existing_couple(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    patterns = [
        r"\bпартн[её]р\s*[ab]\b",
        r"\bоба\s+партн[её]ра\b",
        r"\bмежду\s+партн[её]рами\b",
        r"\bих\s+отношени",
        r"\bтекущ\w*\s+отношени",
        r"\bразрыв\b",
        r"\bссора\b",
        r"\bпара\b",
        r"\bу\s+не[её]\s+и\s+у\s+него\b",
    ]
    return any(re.search(p, t) for p in patterns)


async def _realign_six_cards_for_single_seeker(
    *,
    question: str,
    cards: list[dict[str, Any]],
    summary: str,
    overall: str,
    advice: str,
    question_essence: str,
    user_id: int,
    profile_id: int | None,
) -> dict[str, Any] | None:
    cards_text = "\n".join(
        [
            (
                f"- position: {c.get('position', i)}\n"
                f"  position_name: {c.get('position_name', '')}\n"
                f"  card_id: {c.get('card_id', '')}\n"
                f"  card_name: {c.get('card_name', '')}\n"
                f"  is_reversed: {bool(c.get('is_reversed', False))}\n"
                f"  interpretation: {str(c.get('interpretation', '')).strip()}"
            )
            for i, c in enumerate(cards)
        ]
    )
    prompt = (
        "Ты редактор таро-расклада. Важно: вопрос пользователя про возможность новых отношений, а не про текущую пару.\n"
        f"Вопрос: {question}\n\n"
        "Нужно исправить интерпретацию так, чтобы она строго соответствовала вопросу:\n"
        "- НЕ предполагай существующего партнёра/пару;\n"
        "- НЕ используй формулировки про текущий разрыв/конфликт пары;\n"
        "- позиции 1 и 2 трактуй как «Она» и «Он» в контексте потенциального знакомства;\n"
        "- сохраняй card_id/card_name/position/position_name буквально.\n\n"
        "Текущий вариант:\n"
        f"summary: {summary}\n"
        f"overall: {overall}\n"
        f"question_essence: {question_essence}\n"
        f"advice: {advice}\n\n"
        "cards_interpretations:\n"
        f"{cards_text}\n\n"
        "Верни строго JSON:\n"
        "{"
        '"cards_interpretations":[{"position":0,"position_name":"...","interpretation":"...","card_id":"...","card_name":"...","is_reversed":false}],'
        '"summary":"...",'
        '"overall":"...",'
        '"question_essence":"...",'
        '"advice":"..."'
        "}"
    )
    try:
        raw = await ai_client.generate_text(
            prompt,
            system_prompt=get_tarot_expert_system_prefix(),
            max_tokens=2200,
            user_id=user_id,
            profile_id=profile_id,
            feature_type="tarot_six_cards_realign",
            model_override=_tarot_interpretation_model_override(),
        )
        parsed = _parse_json_object(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("tarot six_cards realign failed: %s", exc)
        return None


def _tarot_result_payload_text(
    *,
    cards: list[dict[str, Any]],
    summary: str,
    overall: str,
    question_essence: str,
    advice: str,
) -> str:
    cards_text = "\n".join(
        [
            (
                f"- position: {c.get('position', i)}\n"
                f"  position_name: {c.get('position_name', '')}\n"
                f"  card_id: {c.get('card_id', '')}\n"
                f"  card_name: {c.get('card_name', '')}\n"
                f"  interpretation: {str(c.get('interpretation', '')).strip()}"
            )
            for i, c in enumerate(cards or [])
        ]
    )
    return (
        f"summary: {summary}\n"
        f"overall: {overall}\n"
        f"question_essence: {question_essence}\n"
        f"advice: {advice}\n\n"
        f"cards_interpretations:\n{cards_text}"
    )


async def _is_tarot_answer_aligned(
    *,
    question: str,
    spread_code: str,
    spread_name: str,
    cards: list[dict[str, Any]],
    summary: str,
    overall: str,
    question_essence: str,
    advice: str,
    user_id: int,
    profile_id: int | None,
) -> tuple[bool, str]:
    payload_text = _tarot_result_payload_text(
        cards=cards,
        summary=summary,
        overall=overall,
        question_essence=question_essence,
        advice=advice,
    )
    prompt = (
        "Проверь соответствие интерпретации вопросу пользователя.\n"
        f"Вопрос: {question}\n"
        f"Расклад: {spread_name} ({spread_code})\n\n"
        "Критерии несоответствия:\n"
        "- ответ уходит в другую тему;\n"
        "- делает неподтверждённые допущения, противоречащие вопросу;\n"
        "- игнорирует формулировку вопроса и ключевые ограничения.\n\n"
        "Текущий ответ:\n"
        f"{payload_text}\n\n"
        "Верни строго JSON: {\"aligned\": true|false, \"reason\": \"кратко\"}."
    )
    try:
        raw = await ai_client.generate_text(
            prompt,
            system_prompt="Ты проверяешь качество и релевантность таро-ответа. Отвечай только JSON.",
            max_tokens=260,
            user_id=user_id,
            profile_id=profile_id,
            feature_type="tarot_answer_check",
        )
        parsed = _parse_json_object(raw)
        aligned = bool(parsed.get("aligned")) if isinstance(parsed, dict) else True
        reason = str(parsed.get("reason") or "").strip() if isinstance(parsed, dict) else ""
        return aligned, reason
    except Exception as exc:
        logger.warning("tarot alignment check failed: %s", exc)
        return True, ""


async def _realign_tarot_answer_to_question(
    *,
    question: str,
    spread_code: str,
    spread_name: str,
    cards: list[dict[str, Any]],
    summary: str,
    overall: str,
    question_essence: str,
    advice: str,
    user_id: int,
    profile_id: int | None,
) -> dict[str, Any] | None:
    payload_text = _tarot_result_payload_text(
        cards=cards,
        summary=summary,
        overall=overall,
        question_essence=question_essence,
        advice=advice,
    )
    prompt = (
        "Отредактируй таро-ответ так, чтобы он строго соответствовал вопросу пользователя.\n"
        f"Вопрос: {question}\n"
        f"Расклад: {spread_name} ({spread_code})\n\n"
        "Правила:\n"
        "- не добавляй неподтверждённых допущений;\n"
        "- сохраняй фокус на вопросе в summary/overall/advice;\n"
        "- не меняй card_id/card_name/position/position_name;\n"
        "- в каждой карте оставь интерпретацию в контексте вопроса;\n"
        "- не сокращай толкования карт до одной фразы: сохраняй развёрнутый текст; если символика и детали изображения уже вплетены в смысл, сохрани их; при правке дополняй по смыслу, а не ужимай; в тексте для пользователя не используй длинное тире.\n\n"
        "Текущий вариант:\n"
        f"{payload_text}\n\n"
        "Верни строго JSON:\n"
        "{"
        '"cards_interpretations":[{"position":0,"position_name":"...","interpretation":"...","card_id":"...","card_name":"...","is_reversed":false}],'
        '"summary":"...",'
        '"overall":"...",'
        '"question_essence":"...",'
        '"advice":"..."'
        "}"
    )
    try:
        raw = await ai_client.generate_text(
            prompt,
            system_prompt=get_tarot_expert_system_prefix(),
            max_tokens=3200,
            user_id=user_id,
            profile_id=profile_id,
            feature_type=f"tarot_realign_{spread_code}",
            model_override=_tarot_interpretation_model_override(),
        )
        parsed = _parse_json_object(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("tarot realign by question failed: %s", exc)
        return None


def _fallback_follow_up_questions(question: str) -> list[str]:
    third_person = _question_is_third_person(question)
    sets_self = [
        [
            "Вы уже предпринимали конкретные шаги по этой теме?",
            "Сейчас для вас важнее стабильность, чем быстрый результат?",
            "Вы готовы действовать в ближайшие 7 дней?",
        ],
        [
            "У вас есть чёткий критерий, по которому вы поймёте, что движетесь верно?",
            "В этой ситуации вас больше сдерживает страх ошибки, чем нехватка ресурсов?",
            "Вы готовы начать с малого теста, а не с большого рывка?",
        ],
        [
            "Вы обсуждали это решение с человеком, который реально влияет на результат?",
            "Сейчас у вас есть хотя бы один ресурс, на который можно опереться уже сегодня?",
            "Вы готовы временно отказаться от второстепенного ради главной цели?",
        ],
    ]
    sets_third = [
        [
            "Он уже предпринимал конкретные шаги по этой теме?",
            "Сейчас для него важнее стабильность, чем быстрый результат?",
            "Он готов действовать в ближайшие 7 дней?",
        ],
        [
            "У него есть чёткий критерий, по которому он поймёт, что движется верно?",
            "В этой ситуации его больше сдерживает страх ошибки, чем нехватка ресурсов?",
            "Он готов начать с малого теста, а не с большого рывка?",
        ],
        [
            "Он обсуждал это решение с человеком, который реально влияет на результат?",
            "Сейчас у него есть хотя бы один ресурс, на который можно опереться уже сегодня?",
            "Он готов временно отказаться от второстепенного ради главной цели?",
        ],
    ]
    q = (question or "").strip().lower()
    seed = int(sha1(q.encode("utf-8")).hexdigest()[:8], 16) if q else random.randint(0, 10_000_000)
    bank = sets_third if third_person else sets_self
    return bank[seed % len(bank)]


async def _ai_backfill_interpretation(
    *,
    card_name: str,
    card_id: str,
    position_name: str,
    is_reversed: bool,
    question: str,
    spread_name: str,
    visual_desc: str,
    user_id: int,
    profile_id: int | None,
) -> str:
    """Generate per-card interpretation when batch JSON is missing/invalid."""
    label = _card_display_label(card_name, card_id) or card_name or card_id or "Карта"
    orientation = "перевернутая карта" if is_reversed else "прямая карта"
    visual_part = f"\nНа карте изображено: {visual_desc[:900]}" if visual_desc else ""
    prompt = (
        "Сделай толкование одной карты таро на русском языке.\n"
        f"Расклад: {spread_name}\n"
        f"Позиция: {position_name}\n"
        f"Вопрос пользователя: {question or 'Общий запрос'}\n"
        f"Карта: {label} ({orientation})\n"
        f"{visual_part}\n\n"
        "Требования:\n"
        "- Пользователь уже видит картинку: не пересказывай подряд, что на иллюстрации. Если передано описание изображения карты, вплетай его в толкование (стихии, жесты, символы, цвет, композиция) как усилители смысла для позиции и вопроса. Всего не меньше 5 предложений, без одной короткой фразы вместо расклада;\n"
        "- без шаблона «карта в позиции», без «зафиксировать шаг»;\n"
        "- без JSON, без markdown, только готовый текст; без длинного тире в тексте для пользователя.\n"
    )
    try:
        text = await ai_client.generate_text(
            prompt,
            system_prompt=get_tarot_expert_system_prefix(),
            max_tokens=800,
            user_id=user_id,
            profile_id=profile_id,
            feature_type="tarot_card_backfill",
            model_override=_tarot_interpretation_model_override(),
        )
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        return cleaned
    except Exception as exc:
        logger.warning("tarot draw-batch per-card backfill failed for %s: %s", card_id, exc)
        return ""


def _normalize_card_key(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"\.(jpg|jpeg|png|webp)$", "", raw)
    return re.sub(r"[^a-z0-9]+", "", raw)


def _load_tarot_descriptions() -> dict[str, Any]:
    """Load card vision descriptions produced by card-scan pipeline."""
    global _TAROT_DESCRIPTIONS_CACHE, _TAROT_DECK_NORM_CACHE
    if _TAROT_DESCRIPTIONS_CACHE is not None:
        return _TAROT_DESCRIPTIONS_CACHE
    try:
        from pathlib import Path

        data_path = Path(__file__).resolve().parent.parent / "data" / "tarot_card_descriptions.json"
        if data_path.exists():
            loaded = json.loads(data_path.read_text(encoding="utf-8"))
            _TAROT_DESCRIPTIONS_CACHE = loaded if isinstance(loaded, dict) else {}
            _TAROT_DECK_NORM_CACHE = {}
            return _TAROT_DESCRIPTIONS_CACHE
    except Exception:
        logger.exception("Failed to load tarot card descriptions JSON")
    _TAROT_DESCRIPTIONS_CACHE = {}
    _TAROT_DECK_NORM_CACHE = {}
    return _TAROT_DESCRIPTIONS_CACHE


def _get_normalized_deck_descriptions(descriptions: dict[str, Any], deck_id: str) -> dict[str, str]:
    """Lazily build and cache normalized card descriptions per deck."""
    global _TAROT_DECK_NORM_CACHE
    if deck_id in _TAROT_DECK_NORM_CACHE:
        return _TAROT_DECK_NORM_CACHE[deck_id]
    deck_desc = descriptions.get(deck_id)
    if not isinstance(deck_desc, dict):
        _TAROT_DECK_NORM_CACHE[deck_id] = {}
        return _TAROT_DECK_NORM_CACHE[deck_id]
    normalized = {_normalize_card_key(k): v for k, v in deck_desc.items() if isinstance(v, str)}
    _TAROT_DECK_NORM_CACHE[deck_id] = normalized
    return normalized


def _find_visual_description(
    descriptions: dict[str, Any], deck_id: str, card_id: str, card_name: str = ""
) -> str:
    if not isinstance(descriptions, dict):
        return ""
    normalized_id = _normalize_card_key(card_id)
    normalized_name = _normalize_card_key(card_name)

    by_norm = _get_normalized_deck_descriptions(descriptions, deck_id)
    if normalized_id and by_norm.get(normalized_id):
        return str(by_norm[normalized_id]).strip()
    if normalized_name and by_norm.get(normalized_name):
        return str(by_norm[normalized_name]).strip()
    # Не ищем по всем колодам: у разных колод часто одинаковые имена файлов (например 29-Wands8),
    # а описания разные. Чужая колода даст неверный «визуал».
    return ""


async def _fetch_visual_from_image(
    image_url: str,
    card_name: str,
    user_id: int,
    profile_id: int | None,
) -> str:
    """Fetch card image and get vision-based description when no cached description exists."""
    url = (image_url or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return ""
    if not await _is_safe_external_image_url(url):
        logger.warning("tarot image blocked by URL safety policy: %s", url[:120])
        incr_counter("tarot_vision_url_blocked_total")
        return ""
    if await _is_vision_circuit_open():
        incr_counter("tarot_vision_cb_short_circuit_total")
        return ""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            image_bytes = r.content
        if not image_bytes or len(image_bytes) > 5_000_000:  # 5MB max
            return ""
        prompt = (
            "Опиши на русском в 2-4 предложениях что изображено на этой карте таро: фигуры, символы, сюжет, ключевые детали иллюстрации. "
            "Верни строго JSON: {\"description\": \"твой текст\"}."
        )
        raw = await ai_client.analyze_image(
            image_bytes,
            prompt,
            system_prompt="Ты описываешь иллюстрации карт таро. Отвечай только JSON.",
            user_id=user_id,
            profile_id=profile_id,
            feature_type="tarot_card_vision",
        )
        await _vision_circuit_success()
        if isinstance(raw, dict) and raw.get("description"):
            return str(raw["description"]).strip()[:700]
        if isinstance(raw, dict) and raw.get("raw"):
            return str(raw["raw"]).strip()[:700]
        return ""
    except Exception as exc:
        await _vision_circuit_failure()
        logger.debug("tarot image vision fallback failed for %s: %s", url[:80], exc)
        return ""


async def _is_safe_external_image_url(url: str) -> bool:
    """
    Basic SSRF guard:
    - allow only http/https
    - block localhost/private/link-local/multicast/reserved IPs
    - optional host allowlist via TAROT_IMAGE_ALLOWED_HOSTS (comma-separated)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    allowed_raw = (get_settings().TAROT_IMAGE_ALLOWED_HOSTS or "").strip()
    if allowed_raw:
        allowlist = {h.strip().lower() for h in allowed_raw.split(",") if h.strip()}
        if host not in allowlist:
            return False

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or 443, type=socket.SOCK_STREAM)
    except Exception:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


async def _is_vision_circuit_open() -> bool:
    global _VISION_CB_OPEN_UNTIL_MONO
    async with _VISION_CB_LOCK:
        return time.monotonic() < _VISION_CB_OPEN_UNTIL_MONO


async def _vision_circuit_success() -> None:
    global _VISION_CB_CONSECUTIVE_FAILS, _VISION_CB_OPEN_UNTIL_MONO
    async with _VISION_CB_LOCK:
        _VISION_CB_CONSECUTIVE_FAILS = 0
        _VISION_CB_OPEN_UNTIL_MONO = 0.0


async def _vision_circuit_failure() -> None:
    global _VISION_CB_CONSECUTIVE_FAILS, _VISION_CB_OPEN_UNTIL_MONO
    async with _VISION_CB_LOCK:
        _VISION_CB_CONSECUTIVE_FAILS += 1
        incr_counter("tarot_vision_fail_total")
        if _VISION_CB_CONSECUTIVE_FAILS >= _VISION_CB_FAIL_THRESHOLD:
            _VISION_CB_OPEN_UNTIL_MONO = time.monotonic() + _VISION_CB_COOLDOWN_SEC
            incr_counter("tarot_vision_cb_open_total")
            _VISION_CB_CONSECUTIVE_FAILS = 0


def _card_display_label(card_name: str, card_id: str) -> str:
    """Человекочитаемая подпись для фразы «Карта «…» в позиции …». Если имя негодное - возвращаем пустую строку (тогда на бэкенде/фронте пишем просто «Карта»)."""
    name = (card_name or card_id or "").strip()
    if not name or name == "Карта":
        return ""
    if re.match(r"^Карта\s*\d+$", name, re.I) or re.match(r"^\d+$", name):
        return ""
    if re.search(r"\.(jpg|jpeg|png|webp)$", name, re.I):
        return ""
    if re.search(r"[\\/]", name):
        return ""
    if re.search(r"^(rws[_ -]?tarot|wands\d+|cups\d+|swords\d+|pentacles\d+|disks\d+)\b", name, re.I):
        return ""
    if name in {"Жезлов", "Кубков", "Мечей", "Пентаклей", "Дисков", "Монет"}:
        return f"Туз {name}"
    return name


def _is_major(card_id: str) -> bool:
    return (card_id or "").lower().startswith("major")


# Стандартные названия карт по индексу 0-77 (0-21 старшие арканы, 22-35 жезлы, 36-49 кубки, 50-63 мечи, 64-77 пентакли). Для колод с собственными подписями (напр. Page of Presents) толкование даём по стандартной карте.
TAROT_MAJOR_EN = (
    "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
    "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
    "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World",
)
TAROT_RANK_EN = ("", "Ace", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King")
TAROT_SUIT_EN = ("", "Wands", "Cups", "Swords", "Pentacles")


def _card_index_from_id(card_id: str) -> int | None:
    """Извлекает индекс карты 0-77 из card_id (например 74-Page of Presents.jpg -> 74)."""
    if not card_id:
        return None
    raw = re.sub(r"\.(jpg|jpeg|png|webp)$", "", card_id, flags=re.I).strip()
    m = re.match(r"^(\d+)", raw)
    if m:
        n = int(m.group(1))
        if 0 <= n <= 77:
            return n
    # Rider-Waite assets often look like RWS_Tarot_07_Chariot or RWS_Tarot_20_Judgement.
    m = re.search(r"(?:^|[_\-\s])(\d{1,2})(?:[_\-\s]|$)", raw)
    if m:
        n = int(m.group(1))
        if 0 <= n <= 77:
            return n
    return None


def _standard_card_name_en(index: int) -> str:
    """Стандартное английское название карты по индексу 0-77 (для толкования по традиции)."""
    if index < 0 or index > 77:
        return ""
    if index <= 21:
        return TAROT_MAJOR_EN[index]
    suit_idx = (index - 22) // 14
    rank = (index - 22) % 14 + 1
    suit = TAROT_SUIT_EN[suit_idx + 1]
    rank_name = TAROT_RANK_EN[rank]
    return f"{rank_name} of {suit}"


def _standard_card_name_ru(index: int) -> str:
    if index < 0 or index > 77:
        return ""
    major_ru = (
        "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
        "Иерофант", "Влюблённые", "Колесница", "Сила", "Отшельник",
        "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть", "Умеренность",
        "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
    )
    if index <= 21:
        return major_ru[index]
    suit_idx = (index - 22) // 14
    rank = (index - 22) % 14 + 1
    suit = ("Жезлов", "Кубков", "Мечей", "Пентаклей")[suit_idx]
    rank_name = {
        1: "Туз",
        2: "Двойка",
        3: "Тройка",
        4: "Четвёрка",
        5: "Пятёрка",
        6: "Шестёрка",
        7: "Семёрка",
        8: "Восьмёрка",
        9: "Девятка",
        10: "Десятка",
        11: "Паж",
        12: "Рыцарь",
        13: "Королева",
        14: "Король",
    }.get(rank, "")
    return f"{rank_name} {suit}".strip()


async def _resolve_profile(
    db: AsyncSession, user_id: int, profile_id: int | None
) -> None:
    """TARO: personalization by natal profile disabled."""
    _ = db, user_id, profile_id
    return None


def _prepare_single_card(payload: DrawBatchRequest) -> BatchCard:
    names_by_key = {
        _normalize_card_key(str(k)): str(v).strip()
        for k, v in (payload.deck_card_names or {}).items()
        if str(k).strip() and str(v).strip()
    }
    # В single карту выбирает пользователь на фронте. Сервер не должен перекидывать карту,
    # иначе картинка и толкование расходятся.
    if payload.cards:
        src = payload.cards[0]
        picked = src.card_id or src.card_name or random.choice(SINGLE_POOL)
        human_name = (
            names_by_key.get(_normalize_card_key(picked))
            or src.card_name
            or _single_card_human_label({"card_id": picked, "card_name": ""})
        )
        return BatchCard(
            card_id=picked,
            position=0,
            position_name=src.position_name or "Сегодня",
            is_reversed=bool(src.is_reversed) if payload.allow_reversed else False,
            card_name=human_name if human_name and human_name != "эта карта" else picked,
            image=src.image,
        )
    if payload.deck_card_ids:
        picked = random.choice(payload.deck_card_ids)
    else:
        picked = random.choice(SINGLE_POOL)
    reversed_state = bool(payload.allow_reversed and random.random() < 0.5)
    human_name = names_by_key.get(_normalize_card_key(picked)) or _single_card_human_label({"card_id": picked, "card_name": ""})
    card_name = human_name if human_name and human_name != "эта карта" else picked
    return BatchCard(
        card_id=picked,
        position=0,
        position_name="Сегодня",
        is_reversed=reversed_state,
        card_name=card_name,
    )


@router.post("/draw-batch", response_model=DrawBatchResponse)
async def tarot_draw_batch(
    payload: DrawBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> DrawBatchResponse:
    logger.info("tarot draw-batch: spread=%s cards=%s", payload.spread_code, len(payload.cards or []))
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")

    spread_code = payload.spread_code.strip().lower()
    if spread_code not in SPREADS:
        raise HTTPException(status_code=400, detail="Неизвестный расклад.")
    user = await check_limits(db, user_id, "tarot", usage_key=spread_code)
    profile = None

    cards: list[BatchCard]
    if spread_code == "single":
        cards = [_prepare_single_card(payload)]
    else:
        cards = payload.cards
        if not cards:
            raise HTTPException(status_code=422, detail="Для пакетного расклада нужны выбранные карты.")

    normalized_cards = []
    for c in cards:
        normalized_cards.append(
            BatchCard(
                card_id=c.card_id,
                position=c.position,
                position_name=c.position_name,
                is_reversed=bool(c.is_reversed) if payload.allow_reversed else False,
                card_name=c.card_name,
                image=c.image,
            )
        )
    cards = normalized_cards

    descriptions = _load_tarot_descriptions()
    deck_id = (payload.deck or "classic").strip().lower()
    if deck_id and deck_id not in descriptions:
        logger.info(
            "tarot draw-batch: deck_id %r has no cached descriptions (keys sample: %s); визуал из JSON недоступен, возможен vision или только standard_card",
            deck_id,
            list(descriptions.keys())[:8],
        )
    sorted_cards = sorted(cards, key=lambda x: x.position)
    # «Три карты»: полный промпт и лимиты, иначе fast_mode даёт урезанный JSON и часто уходит в шаблон «Пауза и внутренний тормоз».
    fast_mode = spread_code == "single"

    # Resolve visual descriptions: cached first, then vision API for cards with image but no cached (все расклады, включая single/three_cards)
    image_resolved: dict[str, str] = {}
    tasks = []
    keys: list[str] = []
    for c in sorted_cards:
        # Ускоряем "Карту дня": для single не запускаем vision fallback по URL изображения.
        # Это часто самый дорогой этап и не обязателен для краткого одно-карточного расклада.
        if spread_code == "single":
            continue
        cached = _find_visual_description(descriptions, deck_id, c.card_id, c.card_name)
        if cached and cached.strip():
            continue
        if not (c.image and str(c.image).strip().startswith(("http://", "https://"))):
            continue
        card_key = _normalize_card_key(c.card_id or c.card_name or str(c.position)) or str(c.position)
        tasks.append(
            _fetch_visual_from_image(
                str(c.image),
                c.card_name or c.card_id or "",
                user_id,
                profile.id if profile else None,
            )
        )
        keys.append(card_key)
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for k, r in zip(keys, results):
            if isinstance(r, str) and r.strip():
                image_resolved[k] = r.strip()[:700]
            elif isinstance(r, Exception):
                logger.debug("tarot vision fallback for key %s: %s", k, r)

    def _visual_line(c: BatchCard) -> str:
        visual_desc = _find_visual_description(descriptions, deck_id, c.card_id, c.card_name)
        if not (visual_desc and visual_desc.strip()):
            card_key = _normalize_card_key(c.card_id or c.card_name or str(c.position)) or str(c.position)
            visual_desc = image_resolved.get(card_key, "")
        if not (visual_desc and visual_desc.strip()):
            return ""
        return f"\n  на карте изображено: {visual_desc.strip()[:700]}"

    def _standard_line(c: BatchCard) -> str:
        # Если есть описание изображения карты: не подмешивать «классическую» сцену:
        # модель иначе описывает RWS вместо реальной иллюстрации.
        cached_viz = _find_visual_description(descriptions, deck_id, c.card_id, c.card_name)
        ck = _normalize_card_key(c.card_id or c.card_name or str(c.position)) or str(c.position)
        if (cached_viz and cached_viz.strip()) or image_resolved.get(ck):
            return ""
        idx = _card_index_from_id(c.card_id)
        if idx is not None:
            standard_en = _standard_card_name_en(idx)
            if standard_en:
                return f"\n  standard_card: {standard_en} (по номеру карты - толкуй по смыслу этой карты из традиции/учебников)"
        return ""

    cards_prompt = "\n".join(
        [
            (
                f"- Позиция: {c.position_name}\n"
                f"  card_id: {c.card_id}\n"
                f"  card_name: {c.card_name or c.card_id}\n"
                f"  card_type: {get_tarot_card_type(c.card_name or '', c.card_id)}\n"
                f"  перевернута: {'да' if c.is_reversed else 'нет'}\n"
                f"  ключи: {'тень, внутреннее препятствие, задержка' if c.is_reversed else 'прямое проявление, ресурс, движение'}"
                + _standard_line(c)
                + _visual_line(c)
            )
            for c in sorted_cards
        ]
    )
    deep_dialog = SPREADS[spread_code]["deep"]
    spread_rule = SPREAD_ANALYSIS_RULES.get(spread_code, "")
    follow_up_rule = (
        "Сформируй ровно 3 уточняющих вопроса по теме вопроса пользователя. "
        "Каждый вопрос должен допускать только один из трёх ответов: Да, Нет или Не знаю. "
        "Формулируй кратко и по существу. Используй тот же субъект, что и в вопросе пользователя: "
        "если вопрос о друге/партнёре/третьем лице, пиши про него (он/она/у него), а не про пользователя. "
        "Избегай повторяющихся шаблонов между раскладами. "
        "Верни в follow_up_questions массив ровно из 3 строк."
        if deep_dialog
        else "Сформируй 0-1 уточняющий вопрос."
    )
    user_name = (profile.name or "").strip() if profile and profile.name else ""
    age_hint = ""
    if profile and profile.birth_date:
        try:
            today = datetime.now(timezone.utc).date()
            age_years = today.year - profile.birth_date.year - (
                (today.month, today.day) < (profile.birth_date.month, profile.birth_date.day)
            )
            age_hint = age_style_instruction(age_years) if age_years >= 0 else ""
        except Exception:
            age_hint = ""
    naming_rule = (
        f"Иногда естественно обращайся по имени «{user_name}» (1-2 раза в summary/overall), без избыточных повторов и без канцелярита."
        if user_name
        else "Обращайся естественно и нейтрально, без искусственных обращений."
    )
    financial_rule = (
        "Это финансовый расклад: в поле advice дай конкретный план или рекомендации по деньгам, строго исходя из карт и вопроса пользователя. "
        "Формат на твоё усмотрение: одно предложение, 2-3 коротких шага или мини-план; не привязывайся к шаблону «один шаг на 7 дней». "
        "Каждый новый расклад должен отличаться по формулировкам и структуре совета."
        if spread_code == "financial"
        else ""
    )
    relationship_rule = ""
    if spread_code == "six_cards":
        if _question_implies_no_current_partner(payload.question or ""):
            relationship_rule = (
                "Это расклад про возможность новых отношений (в вопросе нет текущего партнёра). "
                "Не пиши про уже существующую пару и не описывай 'взаимодействие партнёров' как факт. "
                "Интерпретируй позиции так: 1 - эмоциональная готовность пользователя, 2 - вероятный тип/намерения потенциального партнёра, "
                "3 - сценарий ближайшего знакомства/контакта, 4 - что поможет сближению, 5 - что мешает, 6 - итог/вероятность в указанный срок. "
                "Избегай формулировок про 'разрыв', 'текущий конфликт пары' и других предположений о наличии отношений."
            )
        else:
            relationship_rule = (
                "Это расклад про текущую или формирующуюся пару: в позициях 1 и 2 используй формулировки 'Она' и 'Он' (без 'партнёр A/B')."
            )
    _simple_spread = spread_code in ("single", "three_cards")
    task1_line = (
        "1) Для каждой карты: не меньше 4 предложений.\n\n"
        f"{TAROT_BATCH_PER_CARD_INTERPRETATION_RULES}\n\n"
        "При интерпретации каждой карты строго следуй правилам:\n"
        "- Старший Аркан: описывай личность, урок или глубинный смысл.\n"
        "- Придворный Аркан: описывай человека (характер, роль, возраст).\n"
        "- Младший Аркан (числовой): описывай ситуацию, событие, динамику, обстоятельства. Не описывай человека.\n"
        "Если карта перевёрнутая: учитывай теневой аспект по типу карты (блокировка/искажение для Старших, негативное влияние для Придворных, препятствия и задержки для Младших).\n"
        "Если есть описание изображения карты, не пересказывай рисунок подряд: вплетай символы в смысл. Итого 4-10 предложений на карту. Запрещено выдавать одну короткую фразу вместо толкования. Не начинай с шаблона «карта в позиции».\n"
        if _simple_spread
        else "1) Для каждой карты дай развёрнутое толкование в контексте позиции и вопроса.\n\n"
        f"{TAROT_BATCH_PER_CARD_INTERPRETATION_RULES}\n\n"
        "При интерпретации каждой карты строго следуй правилам:\n"
        "- Старший Аркан: описывай личность, урок или глубинный смысл.\n"
        "- Придворный Аркан: описывай человека (характер, роль, возраст).\n"
        "- Младший Аркан (числовой): описывай ситуацию, событие, динамику, обстоятельства. Не описывай человека.\n"
        "Если карта перевёрнутая: учитывай теневой аспект по типу карты (блокировка/искажение для Старших, негативное влияние для Придворных, препятствия и задержки для Младших).\n"
        "Объём разный: одни карты 3-5 предложений, другие 5-8. Пиши содержательно, с образами и практическим смыслом.\n"
    )
    task2_line = (
        "2) Поля summary и overall: следуй блоку «Правила синтеза итога» выше (в summary 1-2 фразы, в overall 4-7 предложений синтеза без разбора каждой карты по отдельности).\n"
        if _simple_spread
        else "2) Поля summary и overall: следуй блоку «Правила синтеза итога» выше; для финансового расклада summary = короткий вывод, overall = развёрнутый синтез.\n"
    )
    task21_line = (
        "2.1) Покажи, как карты связаны, простыми словами (что было, что сейчас, к чему ведёт), без сложных терминов.\n"
        if _simple_spread
        else "2.1) Критично для ВСЕХ раскладов: покажи, как карты цепляются друг за друга (причина и следствие, кто усиливает кого, где трение), учитывай повтор мастей/арканов и контраст соседних позиций. Пиши простым языком, не как учебник.\n"
    )
    prompt = (
        "Ты опытный таролог в современном стиле. "
        f"Вопрос пользователя: {payload.question or 'Общий запрос'}. "
        f"Расклад: {SPREADS[spread_code]['name']}.\n"
        "Карты:\n"
        f"{cards_prompt}\n\n"
        f"{TAROT_SUMMARY_OVERALL_RULES}\n\n"
        f"Контекст и правила для этого типа расклада:\n{spread_rule}\n\n"
        "Задачи:\n"
        "0) Во всех текстовых полях для пользователя не используй длинное тире: вместо него двоеточие, запятая или дефис.\n"
        f"{task1_line}"
        "1.0) Критично: в толковании каждой карты используй только то название карты (card_name), которое передано в этой карточке в «Карты:». Не подставляй другое название карты (например, не пиши «Иерофант», если в карточке указана «Queen of Wands» / «Королева Жезлов»).\n"
        "1.1) Описание изображения карты критично: если передана строка «на карте изображено», опирайся на неё как на источник символики и смыслов, не как на текст для пересказа пользователю. Фигуры, жесты, предметы, стихии, символы и композиция влияют на толкование. Поле interpretation в JSON: полноценный абзац, не заголовок и не одна строка.\n"
        "1.12) Если описание изображения непустое, запрещено описывать стандартную иллюстрацию Rider-Waite или любую другую «учебниковую» сцену, если она не совпадает с описанием в карточке. Не выдумывай человека, башню, шар и т.д., если этого нет в переданном описании.\n"
        "1.13) Любая упоминаемая деталь сцены (свечи, музыка, танцующие фигуры, ангел, труба, толпа и т.д.) должна встречаться **в том же** фрагменте «на карте изображено» для этой карты. Если чего-то нет в этом описании, в толковании этого не упоминай. "
        "Если строки «на карте изображено» в карточке нет: не заполняй пробел выдуманной картинкой, пиши смысл архетипа по card_name и card_type.\n"
        f"{task2_line}"
        f"{task21_line}"
        "3) Дай скрытую суть вопроса (1 предложение).\n"
        + (
            "4) Поле advice: одно короткое тёплое пожелание на день (без слова «совет», без «зафиксировать шаг», без «по фактам»). Критично: overall и advice не совпадают по тексту.\n"
            if spread_code == "single"
            else "4) Поле advice: одно предложение с ясным действием или ориентиром под вопрос, без пустых формулировок «сделай шаг». Критично: overall и advice не совпадают по тексту.\n"
        )
        + f"5) {follow_up_rule}\n"
        f"6) {financial_rule}\n"
        f"7) {naming_rule}\n"
        f"8) {age_hint or 'Пиши нейтрально, без возрастных допущений.'}\n"
        f"9) {relationship_rule}\n"
        "Верни строго JSON со структурой:\n"
        "Критично: в cards_interpretations в каждом элементе скопируй card_id и card_name буквально из списка «Карты» выше (из той карточки, для которой пишешь толкование). "
        "Не переводи и не меняй формат (например 39-Minor-Swords-04 или 26-Minor-Discs-05). Иначе толкование привяжется не к той карте. "
        "position - индекс с нуля: 0 = первая карта, 1 = вторая и т.д.\n"
        "{"
        '"cards":[{"position":1,"position_name":"...","card_name":"...","interpretation":"...","is_reversed":false}],'
        '"cards_interpretations":[{"position":0,"position_name":"...","interpretation":"...","card_id":"...","card_name":"...","is_reversed":false}],'
        '"summary":"...",'
        '"overall":"...",'
        '"question_essence":"...",'
        '"follow_up_questions":["..."],'
        '"advice":"..."'
        "}"
    )
    max_tokens = 5200
    ai_timeout_sec = 60.0
    if fast_mode:
        three_cards_hint = (
            "3 карты: в каждой позиции соблюдай card_type и вплетай описание изображения карты в смысл прошлого/настоящего/будущего и вопроса, без пересказа картинки подряд. "
            "Не используй шаблон «карта в позиции …». Не пиши «общий вопрос», если текст вопроса есть. Без длинного тире в тексте для пользователя.\n"
            if spread_code == "three_cards"
            else ""
        )
        single_hint = (
            "1 карта: 3-5 коротких предложений, примерно на 30% короче прежнего формата.\n\n"
            f"{TAROT_BATCH_PER_CARD_INTERPRETATION_RULES}\n\n"
            "Строго соблюдай классификацию: Старший Аркан: личность/урок/архетип; Придворный Аркан: человек и его роль; "
            "Младший Аркан (числовой): ситуация и динамика, не человек. "
            "Для перевёрнутой карты включай теневой аспект по типу карты.\n"
            "Пользователь видит рисунок, не пересказывай его; вплетай описание изображения карты в смысл дня. "
            "summary: 1 короткое предложение. overall: 3-4 коротких предложения без повторов. "
            "Поле advice: одно тёплое пожелание, не инструкция и не «шаг». Без длинного тире в тексте для пользователя.\n"
            if spread_code == "single"
            else ""
        )
        prompt = (
            "Ты опытный таролог. Верни только JSON без пояснений. "
            "Во всех текстовых полях для пользователя не используй длинное тире.\n"
            "Критично: если у карты в списке есть строка «на карте изображено», не упоминай предметы и сцены, которых там нет (свечи, музыка, танцы, ангел с трубой и т.д.). "
            "Без строки «на карте изображено» не выдумывай картинку карты, только смысл по названию и типу.\n"
            f"Вопрос: {payload.question or 'Общий запрос'}\n"
            f"Расклад: {SPREADS[spread_code]['name']}\n"
            f"Карты:\n{cards_prompt}\n\n"
            f"{TAROT_SUMMARY_OVERALL_RULES}\n\n"
            f"{three_cards_hint}"
            f"{single_hint}"
            "Сделай интерпретации по позициям с учётом card_type, краткий summary, развёрнутый overall по правилам синтеза выше и поле advice: "
            + (
                "для «Карта дня» одно тёплое пожелание на день."
                if spread_code == "single"
                else "короткая поддержка по ситуации, без пустых «сделай шаг»."
            )
            + "\n"
            "JSON-формат:\n"
            "{"
            '"cards_interpretations":[{"position":0,"position_name":"...","interpretation":"...","card_id":"...","card_name":"...","is_reversed":false}],'
            '"summary":"...",'
            '"overall":"...",'
            '"question_essence":"...",'
            '"follow_up_questions":[],'
            '"advice":"..."'
            "}"
        )
        max_tokens = 760
        ai_timeout_sec = 6.5
    system_prompt = get_tarot_expert_system_prefix()
    try:
        raw = await asyncio.wait_for(
            ai_client.generate_text(
                prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                user_id=user_id,
                profile_id=profile.id if profile else None,
                feature_type=f"tarot_{spread_code}",
                model_override=_tarot_interpretation_model_override(),
            ),
            timeout=ai_timeout_sec,
        )
        parsed = _parse_json_object(raw)
        if not parsed and raw.strip():
            logger.warning("tarot draw-batch: AI returned non-JSON or empty object, using fallback interpretations")
            parsed = {}
    except Exception as exc:
        logger.warning("tarot draw-batch AI failed (primary + fallback), returning fallback interpretations: %s", exc)
        parsed = {}

    card_interpretations = parsed.get("cards_interpretations")
    if not isinstance(card_interpretations, list):
        # Backward/forward compatibility:
        # if model returns `cards` according to the new contract, reuse it as interpretations source.
        card_interpretations = parsed.get("cards")
    if not isinstance(card_interpretations, list):
        card_interpretations = []
    normalized = []
    by_pos: dict[int, dict[str, Any]] = {}
    for item in card_interpretations:
        if not isinstance(item, dict):
            continue
        try:
            pos = int(item.get("position", -1))
        except (TypeError, ValueError):
            continue
        by_pos[pos] = item
    # AI может вернуть позиции 1-based (1,2,3). Нормализуем к 0-based по индексу.
    positions_seen = [p for p in by_pos if p >= 0]
    one_based = len(positions_seen) > 0 and all(p >= 1 for p in positions_seen)
    if one_based:
        by_pos = {(p - 1): v for p, v in by_pos.items() if p >= 1}
    # Привязка интерпретации к карте по card_id/card_name (надёжнее, чем только по позиции).
    by_card_key: dict[str, dict[str, Any]] = {}
    for item in card_interpretations:
        if not isinstance(item, dict):
            continue
        key = _normalize_card_key(str(item.get("card_id") or item.get("card_name") or ""))
        if key:
            by_card_key[key] = item
    _PLACEHOLDER_PHRASE = "требует дополнительного размышления"
    for c in sorted(cards, key=lambda x: x.position):
        norm_id = _normalize_card_key(c.card_id or "")
        norm_name = _normalize_card_key(c.card_name or "")
        src = (norm_id and by_card_key.get(norm_id)) or (norm_name and by_card_key.get(norm_name)) or {}
        raw_interp = src.get("interpretation")
        card_name = _safe_text(c.card_name, c.card_id)
        if card_name in {"Жезлов", "Кубков", "Мечей", "Пентаклей", "Дисков", "Монет"}:
            card_name = f"Туз {card_name}"
        position_name = c.position_name or f"Позиция {c.position + 1}"
        raw_str = (raw_interp and str(raw_interp).strip()) or ""
        min_interp_len = 40 if spread_code == "single" else 110
        if raw_str and _PLACEHOLDER_PHRASE not in raw_str.lower() and len(raw_str) >= min_interp_len:
            interpretation = _safe_text(raw_interp, "")
        else:
            label = _card_display_label(card_name, c.card_id)
            card_phrase = f"Карта «{label}»" if label else "Карта"
            if fast_mode:
                show_label = label or card_name or "карта"
                if spread_code == "three_cards":
                    direction = (
                        "Пауза и внутренний тормоз, не дави на себя."
                        if bool(c.is_reversed)
                        else "Можно двигаться спокойно, без лишней суеты."
                    )
                    pos_idx = int(c.position) % 3
                    tail_by_pos = (
                        "Откуда ты пришёл к этой теме и что из прошлого ещё цепляет.",
                        "Что сейчас в твоих руках и где ты реально влияешь на ситуацию.",
                        "Куда качнет, если не ломать всё резко и смотреть шире.",
                    )
                    interpretation = (
                        f"«{show_label}» и зона «{position_name}»: {tail_by_pos[pos_idx]} {direction}"
                    )
                else:
                    human_label = _single_card_human_label(
                        {
                            "card_name": c.card_name,
                            "card_id": c.card_id,
                        }
                    )
                    ctype = get_tarot_card_type(c.card_name or "", c.card_id)
                    interpretation = _single_fast_fallback_interpretation(
                        card_label=human_label or show_label,
                        card_type=ctype,
                        is_reversed=bool(c.is_reversed),
                    )
            else:
                visual_desc = _find_visual_description(descriptions, deck_id, c.card_id, c.card_name)
                if not (visual_desc and visual_desc.strip()):
                    card_key = _normalize_card_key(c.card_id or c.card_name or str(c.position)) or str(c.position)
                    visual_desc = image_resolved.get(card_key, "")
                interpretation = await _ai_backfill_interpretation(
                    card_name=card_name,
                    card_id=c.card_id,
                    position_name=position_name,
                    is_reversed=bool(c.is_reversed),
                    question=payload.question or "",
                    spread_name=SPREADS[spread_code]["name"],
                    visual_desc=visual_desc,
                    user_id=user_id,
                    profile_id=profile.id if profile else None,
                )
                if not interpretation:
                    interpretation = (
                        f"{card_phrase} в зоне «{position_name}» задаёт важный акцент. "
                        "Опирайся на то, что чувствуешь телом, а не на шум в голове."
                    )
        interpretation = _strip_false_reversed_claims(interpretation, bool(c.is_reversed))
        if spread_code == "three_cards":
            interpretation = _strip_three_cards_boilerplate(interpretation)
            interpretation = _sanitize_three_cards_interpretation(
                interpretation,
                position_name=position_name,
                card_name=card_name,
                is_reversed=bool(c.is_reversed),
            )
        normalized.append(
            {
                "position": c.position,
                "position_name": c.position_name,
                "interpretation": interpretation,
                "card_id": c.card_id,
                "card_name": card_name,
                "is_reversed": bool(c.is_reversed),
            }
        )

    single_summary_default = "Сегодня держи фокус на главном и не распыляйся."
    single_overall_default = "Сегодня полезно идти мягким темпом: без рывков, но с ясным вниманием к главному."
    if spread_code == "single":
        primary_card = normalized[0] if normalized else {}
        card_label = _single_card_human_label(primary_card if isinstance(primary_card, dict) else None)
        card_type = ""
        if isinstance(primary_card, dict):
            card_type = get_tarot_card_type(
                str(primary_card.get("card_name") or ""),
                str(primary_card.get("card_id") or ""),
            )
        specific_single_fallback = _single_fast_fallback_interpretation(
            card_label=card_label,
            card_type=card_type,
            is_reversed=bool(primary_card.get("is_reversed")) if isinstance(primary_card, dict) else False,
        )
        interpretation_seed = ""
        if isinstance(primary_card, dict):
            interpretation_seed = _strip_technical_card_tokens(
                str(primary_card.get("interpretation") or "")
            )
        interpretation_seed = _normalize_single_text_style(interpretation_seed)
        interpretation_seed = re.sub(r"\s+", " ", interpretation_seed).strip()
        interpretation_seed = _compact_single_text(interpretation_seed, max_sentences=3, max_chars=150)
        if len(interpretation_seed) > 150:
            interpretation_seed = interpretation_seed[:150].rsplit(" ", 1)[0].rstrip(" ,.;:") + "."
        single_summary_default = specific_single_fallback
        if interpretation_seed:
            single_overall_default = interpretation_seed
        else:
            single_overall_default = specific_single_fallback
    summary = _safe_text(
        parsed.get("summary") or parsed.get("overall"),
        single_summary_default if spread_code == "single" else "Карты показывают сдвиг: есть смысл не торопиться и смотреть, что реально важно.",
    )
    overall = _safe_text(parsed.get("overall"), summary)
    if spread_code == "single" and len((overall or "").strip()) < 80:
        overall = single_overall_default
    if spread_code == "single":
        summary = _strip_direct_position_phrase(_strip_technical_card_tokens(summary))
        overall = _strip_direct_position_phrase(_strip_technical_card_tokens(overall))
        summary = _diversify_single_boilerplate(summary, card_label)
        overall = _diversify_single_boilerplate(overall, card_label)
        low_signal_summary = (
            not summary
            or "карта дня на сегодня" in summary.lower()
            or summary.lower().count("карта дня") > 1
            or _texts_too_similar(summary, "Сегодня лучше без суеты: выбери один важный шаг и доведи его до конца.")
        )
        generic_single_phrases = (
            "фокус дня в практических шагах",
            "управлении текущей ситуацией",
            "опора на практику",
            "ресурс и порядок в делах",
            "спокойное действие и ровный ритм",
            "один конкретный шаг",
            "не давить на себя и не форсировать",
        )
        low_signal_summary = low_signal_summary or any(phrase in summary.lower() for phrase in generic_single_phrases)
        if low_signal_summary:
            summary = single_summary_default
        if any(phrase in overall.lower() for phrase in generic_single_phrases):
            overall = single_overall_default
        if card_label and card_label != "эта карта" and card_label.lower() not in summary.lower():
            orientation_prefix = _reversed_card_label(card_label) if isinstance(primary_card, dict) and bool(primary_card.get("is_reversed")) else card_label
            summary = f"{orientation_prefix}: {summary}"
        if card_label and card_label != "эта карта" and card_label.lower() not in overall.lower():
            orientation_prefix = _reversed_card_label(card_label) if isinstance(primary_card, dict) and bool(primary_card.get("is_reversed")) else card_label
            overall = f"{orientation_prefix}: {overall}"
        summary = _normalize_single_text_style(summary)
        overall = _normalize_single_text_style(overall)
        summary = _compact_single_text(summary, max_sentences=2, max_chars=170)
        overall = _compact_single_text(overall, max_sentences=4, max_chars=430)
    if spread_code == "three_cards":
        # Для 3 карт общий итог всегда должен быть развернутым синтезом всех позиций.
        min_overall_chars = 480
        if len((overall or "").strip()) < min_overall_chars:
            cards_in_order = sorted(
                [x for x in normalized if isinstance(x, dict)],
                key=lambda x: int(x.get("position", 0)),
            )[:3]

            def _shorten_text(value: str, max_len: int = 220) -> str:
                text = str(value or "").strip()
                if not text:
                    return ""
                text = re.sub(r"\s+", " ", text)
                if len(text) <= max_len:
                    return text
                return text[: max_len - 1].rstrip(" ,.;:") + "."

            p1 = cards_in_order[0] if len(cards_in_order) > 0 else {}
            p2 = cards_in_order[1] if len(cards_in_order) > 1 else {}
            p3 = cards_in_order[2] if len(cards_in_order) > 2 else {}
            p1_name = str(p1.get("position_name") or "Прошлое")
            p2_name = str(p2.get("position_name") or "Настоящее")
            p3_name = str(p3.get("position_name") or "Будущее")
            p1_text = _shorten_text(_strip_three_cards_boilerplate(str(p1.get("interpretation") or "")))
            p2_text = _shorten_text(_strip_three_cards_boilerplate(str(p2.get("interpretation") or "")))
            p3_text = _shorten_text(_strip_three_cards_boilerplate(str(p3.get("interpretation") or "")))
            question_text = (payload.question or "").strip()
            question_line = (
                f"К чему вопрос: {question_text}. "
                if question_text
                else ""
            )
            overall = (
                f"{question_line}"
                f"Прошлое («{p1_name}»): {p1_text} "
                f"Сейчас («{p2_name}»): {p2_text} "
                f"Дальше («{p3_name}»): {p3_text} "
                "Три карты вместе складываются в одну историю: прошлое задаёт фон, настоящее показывает, где ты в игре, "
                "а будущее намечает, куда качнётся ситуация, если не паниковать и смотреть шире."
            ).strip()
        if len((summary or "").strip()) < 120:
            summary = (
                "Три карты: что было, тянет в сегодня; что делаешь сейчас, решает, как откроется дальше."
            )
        overall = _dedupe_similar_sentences(_strip_three_cards_boilerplate((overall or "").strip()))
    question_essence = _safe_text(
        parsed.get("question_essence"),
        "В основе вопроса - поиск ясности и внутренней опоры.",
    )
    if spread_code == "financial":
        advice_default = random.choice([
            "Опираясь на карты: выберите один приоритетный денежный шаг и зафиксируйте результат через неделю.",
            "По раскладу: сфокусируйтесь на одном источнике дохода или одном ограничении расходов и оцените эффект.",
            "Исходя из карт: наметьте конкретное действие по финансам и проверьте итог по факту.",
        ])
    elif spread_code == "single":
        advice_default = random.choice(
            [
                "Пусть сегодня будет хотя бы один момент, где ты себе не враг.",
                "Ты уже сделал достаточно, чтобы позволить себе чуть больше воздуха.",
                "Пусть день подкинет маленькую удачу, которую ты заметишь.",
                "Дыши ровнее: иногда это и есть главное, что сейчас можно сделать.",
                "Пусть вечер будет чуть спокойнее, чем ты боишься.",
            ]
        )
    else:
        advice_default = "Смотри на ситуацию чуть мягче: этого порой хватает, чтобы стало легче."
    advice = _safe_text(parsed.get("advice"), advice_default)
    if spread_code == "single":
        advice = _strip_three_cards_boilerplate(advice)
        advice = _strip_direct_position_phrase(_strip_technical_card_tokens(advice))
        advice = _diversify_single_boilerplate(advice, card_label if 'card_label' in locals() else "")
        advice = _normalize_single_text_style(advice)
        if normalized and isinstance(normalized[0], dict):
            prepared_interp = _normalize_single_text_style(
                _diversify_single_boilerplate(
                    _strip_direct_position_phrase(_strip_technical_card_tokens(str(normalized[0].get("interpretation") or ""))),
                    card_label if 'card_label' in locals() else "",
                )
            )
            normalized[0]["interpretation"] = _compact_single_text(prepared_interp, max_sentences=4, max_chars=430) or str(normalized[0].get("interpretation") or "")
    if _texts_too_similar(advice, overall):
        advice = advice_default
    if spread_code == "single" and normalized:
        card_interp = (normalized[0].get("interpretation") or "").strip()
        if card_interp and _texts_too_similar(advice, card_interp):
            advice = advice_default

    # Guardrail for six_cards: if question is about future love/new partner,
    # but text assumes an existing couple, re-align interpretation.
    if spread_code == "six_cards" and _question_implies_no_current_partner(payload.question or ""):
        joined = " ".join(
            [
                summary or "",
                overall or "",
                question_essence or "",
                advice or "",
                " ".join(str(x.get("interpretation") or "") for x in normalized if isinstance(x, dict)),
            ]
        )
        if _text_assumes_existing_couple(joined):
            fixed = await _realign_six_cards_for_single_seeker(
                question=payload.question or "",
                cards=normalized,
                summary=summary,
                overall=overall,
                advice=advice,
                question_essence=question_essence,
                user_id=user_id,
                profile_id=profile.id if profile else None,
            )
            if isinstance(fixed, dict):
                fixed_cards = fixed.get("cards_interpretations")
                if isinstance(fixed_cards, list) and fixed_cards:
                    by_key = {
                        _normalize_card_key(str(x.get("card_id") or x.get("card_name") or "")): x
                        for x in fixed_cards
                        if isinstance(x, dict)
                    }
                    updated = []
                    for c in normalized:
                        k = _normalize_card_key(str(c.get("card_id") or c.get("card_name") or ""))
                        src = by_key.get(k) if k else None
                        if isinstance(src, dict) and str(src.get("interpretation") or "").strip():
                            c = {**c, "interpretation": str(src.get("interpretation")).strip()}
                        updated.append(c)
                    normalized = updated
                summary = _safe_text(fixed.get("summary"), summary)
                overall = _safe_text(fixed.get("overall"), overall)
                question_essence = _safe_text(fixed.get("question_essence"), question_essence)
                advice = _safe_text(fixed.get("advice"), advice)

    # Global guardrail: for any spread with a question, check alignment and re-align if needed.
    q_text = (payload.question or "").strip()
    if q_text and (not fast_mode or spread_code == "three_cards"):
        aligned, _reason = await _is_tarot_answer_aligned(
            question=q_text,
            spread_code=spread_code,
            spread_name=SPREADS[spread_code]["name"],
            cards=normalized,
            summary=summary,
            overall=overall,
            question_essence=question_essence,
            advice=advice,
            user_id=user_id,
            profile_id=profile.id if profile else None,
        )
        if not aligned:
            fixed = await _realign_tarot_answer_to_question(
                question=q_text,
                spread_code=spread_code,
                spread_name=SPREADS[spread_code]["name"],
                cards=normalized,
                summary=summary,
                overall=overall,
                question_essence=question_essence,
                advice=advice,
                user_id=user_id,
                profile_id=profile.id if profile else None,
            )
            if isinstance(fixed, dict):
                fixed_cards = fixed.get("cards_interpretations")
                if isinstance(fixed_cards, list) and fixed_cards:
                    by_key = {
                        _normalize_card_key(str(x.get("card_id") or x.get("card_name") or "")): x
                        for x in fixed_cards
                        if isinstance(x, dict)
                    }
                    updated = []
                    for c in normalized:
                        key = _normalize_card_key(str(c.get("card_id") or c.get("card_name") or ""))
                        src = by_key.get(key) if key else None
                        if isinstance(src, dict) and str(src.get("interpretation") or "").strip():
                            c = {**c, "interpretation": str(src.get("interpretation")).strip()}
                        updated.append(c)
                    normalized = updated
                summary = _safe_text(fixed.get("summary"), summary)
                overall = _safe_text(fixed.get("overall"), overall)
                question_essence = _safe_text(fixed.get("question_essence"), question_essence)
                advice = _safe_text(fixed.get("advice"), advice)
    follow_up_questions = parsed.get("follow_up_questions")
    if not isinstance(follow_up_questions, list):
        follow_up_questions = []
    follow_up_questions = [str(x).strip() for x in follow_up_questions if str(x).strip()]
    if deep_dialog:
        third_person = _question_is_third_person(payload.question or "")
        has_user_pronouns = any(re.search(r"\b(вы|вам|вас|ваш|ваша|ваши)\b", q.lower()) for q in follow_up_questions)
        has_duplicate_questions = len({q.lower() for q in follow_up_questions}) < len(follow_up_questions)
        if (
            not follow_up_questions
            or has_duplicate_questions
            or (third_person and has_user_pronouns)
        ):
            follow_up_questions = _fallback_follow_up_questions(payload.question or "")
    if deep_dialog:
        follow_up_questions = follow_up_questions[:3]
    else:
        follow_up_questions = follow_up_questions[:1]

    persisted = True
    reading = TarotReading(
        user_id=user_id,
        profile_id=profile.id if profile else None,
        spread_code=spread_code,
        question=payload.question or "",
        cards=[c.model_dump() for c in cards],
        cards_interpretations=normalized,
        summary=summary,
        question_essence=question_essence,
        follow_up_questions=follow_up_questions,
        advice=advice,
        chat_history=[],
    )
    user_lock = await _get_draw_batch_user_lock(user_id)
    dist_lock_key = f"tarot:draw-batch:lock:{user_id}"
    lock_wait_started = time.perf_counter()
    dist_lock_token = await cache_acquire_lock(
        dist_lock_key,
        ttl_seconds=25,
        wait_timeout_seconds=2.0,
        retry_delay_ms=80,
    )
    lock_wait_ms = (time.perf_counter() - lock_wait_started) * 1000.0
    incr_counter("tarot_draw_lock_wait_samples_total")
    incr_counter("tarot_draw_lock_wait_ms_total", lock_wait_ms)
    if dist_lock_token is None:
        incr_counter("tarot_draw_lock_contention_total")
        raise HTTPException(status_code=429, detail="Слишком много запросов. Повторите через пару секунд.")
    incr_counter("tarot_draw_lock_acquired_total")
    try:
        async with user_lock:
            # Serialize final billing decision per user to avoid free-slot/deduct races
            await db.execute(
                select(User).where(User.telegram_id == user_id).with_for_update()
            )

            free_no_charge = await has_welcome_free_access(
                db,
                user_id,
                "tarot",
                usage_key=spread_code,
            )

            prior_single_like = await tarot_single_like_usage_today(db, user_id)
            free_daily_single = (
                spread_code == "single"
                and not has_paid_access(user)
                and not free_no_charge
                and prior_single_like == 0
            )

            try:
                db.add(reading)
                await db.flush()
                await increment_daily(db, user_id, "tarot")
                # TARO: расклады бесплатны; списание баланса отключено на этапе запуска.
                await db.commit()
            except HTTPException:
                # Business errors (for example, insufficient balance after concurrent requests)
                # must be returned to client instead of silently converting to free non-persisted response.
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("tarot draw-batch rollback failed after HTTPException")
                raise
            except Exception as exc:
                # Fallback: even if tarot_readings table is unavailable, return AI interpretation.
                # Средства не списываются при сбое сохранения - услуга не состоялась в полной мере.
                logger.exception("tarot draw-batch persistence failed, returning non-persisted response: %s", exc)
                persisted = False
                try:
                    await db.rollback()
                except Exception:
                    await db.rollback()
                    logger.exception("tarot draw-batch rollback failed")
            reading_id = reading.id if persisted else str(uuid4())
            if not persisted:
                try:
                    await cache_set_json(
                        _chat_cache_key(user_id, reading_id),
                        {
                            "question": payload.question or "",
                            "cards": [c.model_dump() for c in cards],
                            "summary": summary,
                            "overall": overall,
                            "advice": advice,
                            "follow_up_questions": follow_up_questions,
                            "chat_history": [],
                        },
                        ttl_seconds=48 * 60 * 60,
                    )
                except Exception:
                    logger.exception("tarot draw-batch fallback cache save failed")
    finally:
        await cache_release_lock(dist_lock_key, dist_lock_token)

    return DrawBatchResponse(
        reading_id=reading_id,
        cards=[c.model_dump() for c in cards],
        cards_interpretations=[CardInterpretation(**x) for x in normalized],
        summary=summary,
        overall=overall,
        question_essence=question_essence,
        follow_up_questions=follow_up_questions,
        advice=advice,
        chat_id=reading_id,
    )


def _tarologist_user_message_is_greeting_only(text: str) -> bool:
    """Короткое приветствие или светская болтовня без вопроса к раскладу: нельзя ставить ready_for_spread."""
    raw = (text or "").strip()
    if not raw or len(raw) > 160:
        return False
    low = raw.lower()
    if re.search(
        r"\b(что|как|когда|где|почему|зачем|какой|какая|какие|сколько|"
        r"любов|отношен|работ|деньг|будущ|судьб|гадан|таро|карт|расклад|"
        r"выйду|уйду|верн|бросит|женится|сделать|выбрать|купить|продать|"
        r"выйти|остаться|поможет|получится|будет\s+ли)\b",
        low,
    ):
        return False
    if "?" in raw:
        return False
    words = re.findall(r"[a-zа-яё]+", low)
    if len(words) > 10:
        return False
    greeting = {
        "привет",
        "здравствуйте",
        "добрый",
        "день",
        "вечер",
        "утро",
        "hello",
        "hi",
        "приветик",
        "салют",
        "хай",
        "hey",
        "доброе",
        "приветствую",
        "спасибо",
        "благодарю",
        "thanks",
        "qq",
        "здрасьте",
    }
    small = greeting | {
        "как",
        "дела",
        "ты",
        "вас",
        "там",
        "ощущения",
        "настроение",
        "у",
        "тебя",
        "вам",
        "твои",
        "ваши",
        "давно",
        "ещё",
        "еще",
        "тут",
        "здесь",
    }
    if not words:
        return True
    if all(w in small for w in words):
        return True
    return False


def _tarologist_last_assistant_message(messages: list[Any]) -> str:
    """Текст последней реплики assistant (messages оканчивается текущим сообщением пользователя)."""
    for m in reversed(messages[:-1]):
        if isinstance(m, dict) and m.get("role") == "assistant":
            return str(m.get("content") or "")
    return ""


def _tarologist_assistant_asked_spread_confirm(text: str) -> bool:
    """В последнем ответе таролога был вопрос о переходе к раскладу (пользователь может ответить «да»)."""
    low = (text or "").lower()
    if "?" not in low:
        return False
    return any(
        x in low
        for x in (
            "расклад",
            "готов",
            "перейти",
            "гадан",
            "карт",
            "хотите",
            "хочешь",
            "приступ",
            "начнём",
            "начнем",
            "разложить",
            "вытянуть",
            "сделать",
        )
    )


def _tarologist_user_message_is_affirmative(text: str) -> bool:
    """Короткое согласие на расклад (после вопроса таролога)."""
    t = (text or "").strip().lower()
    if not t or len(t) > 120:
        return False
    if re.search(r"\b(нет|не хочу|не надо|не нужно|не готов|отмена|стоп)\b", t):
        return False
    if re.match(
        r"^(да|давай|давайте|конечно|хочу|ага|угу|окей|ок|yes|хорошо|начинай|переходи|сделай|делай|вперёд|вперед|поехали|погнали|lf)([!.,\s?]|$)",
        t,
    ):
        return True
    if t in ("да", "давай", "ок", "окей", "угу", "ага", "хорошо", "yes", "lf", "конечно"):
        return True
    return False


def _tarologist_reply_asks_to_start_spread(text: str) -> bool:
    low = (text or "").lower()
    return any(
        x in low
        for x in (
            "выполнить расклад",
            "перейти к раскладу",
            "начать расклад",
            "сделать расклад",
            "разложить карты",
        )
    )


def _tarologist_ten_cards_deep_followup(user_turns: int) -> str:
    if user_turns <= 1:
        return (
            "Чтобы сделать точный Кельтский крест, уточню главное: какая конкретная развилка сейчас перед вами, "
            "и какое решение вы откладываете?"
        )
    if user_turns == 2:
        return (
            "Понял. Ещё один важный фокус: что для вас будет хорошим исходом в этой ситуации через 3-6 месяцев, "
            "и чего вы боитесь больше всего?"
        )
    return (
        "Перед раскладом уточню последний штрих: на что вы готовы опереться уже сейчас, "
        "а что точно не готовы делать ни при каких условиях?"
    )


# Минимум реплик пользователя в чате, после которых сервер может выставить enough_info (автостарт в приложении).
TAROLOGIST_MIN_USER_TURNS_FOR_AUTO: dict[str, int] = {
    # Короткий, но ясный вопрос к картам не должен требовать трёх реплик ради «формы диалога»
    "three_cards": 1,
    "financial": 4,
    "six_cards": 4,
    "ten_cards": 3,
}


def _tarologist_mode_block(spread_id: str) -> str:
    greet_line = (
        "- Если в последнем сообщении только приветствие или светская болтовня без вопроса к раскладу: "
        "ready_for_spread=false; мягко спроси, о чём спросить карты: тема, сфера или выбор.\n"
    )
    if spread_id == "three_cards":
        return (
            "Режим: простой расклад (несколько карт).\n"
            f"{greet_line}"
            "- Уточнения: не больше одного-двух обменов, если вопрос сразу не ясен; не затягивай ради длины диалога.\n"
            "- В одном сообщении не больше одного короткого вопроса пользователю; не перечисляй несколько вопросов подряд.\n"
            "- Уточняй в стиле таролога: сфера (работа, отношения, внутренняя работа), горизонт, что важнее увидеть в раскладе (причина, динамика, совет). "
            "Не веди себя как психолог или коуч: избегай формулировок вроде «что сильнее всего болит», «где больнее всего», «живой контекст страдания».\n"
            "- Если пользователь уже назвал ясную тему или короткий ответ на твоё уточнение (одно слово: лень, страх, он, смена работы): не копай глубже без нужды; перейди к предложению расклада («Выполнить расклад?»), ready_for_spread=false до согласия.\n"
            "- ready_for_spread=true только если в последнем сообщении уже есть осмысленный вопрос для гадания или явное согласие на расклад после твоего приглашения; не затягивай диалог ради формы.\n"
            "- Если спрашивают только время, дату, погоду, курс валют: в reply можно кратко ответить по делу (время см. выше в сообщении системы) или с лёгкой шуткой, затем скажи, что для расклада нужен вопрос к картам про жизненную тему; ready_for_spread=false.\n"
            "- Приветствия без вопроса: ответь по-человечески; ready_for_spread=false, пока не появится вопрос по теме.\n"
            "- refuse_dialog=true только если пользователь после твоих 2-3 вежливых напоминаний продолжает слать явный троллинг или бессмыслицу; в reply честно скажи, что без нормального вопроса не сможешь помочь, но без оскорблений."
        )
    if spread_id == "financial":
        return (
            "Режим: финансовый расклад.\n"
            f"{greet_line}"
            "- Уточнения: обычно от двух до пяти обменов, пока не ясны цель, горизонт и фокус расклада по деньгам; не спеши с ready_for_spread=true.\n"
            "- Уточняй по ситуации простыми словами таролога: про срок («ближайшие недели или дольше»), про источник дохода или ситуацию, без абстракций. "
            "Избегай канцелярита и «маркетинговых» метафор вроде «без тумана», «прозрачно», «вектор», «запрос» в смысле задачи.\n"
            "- Уточняй по ситуации, но в одном сообщении не больше одного короткого вопроса пользователю; не перечисляй несколько вопросов подряд.\n"
            "- Если нужно несколько уточнений, задавай их по очереди в разных сообщениях.\n"
            "- Не лезь в неловкие детали. ready_for_spread=true только когда контекста достаточно для осмысленного расклада; одного короткого «хочу про деньги» мало.\n"
            "- refuse_dialog только при явном тролле после предупреждений."
        )
    if spread_id == "six_cards":
        return (
            "Режим: отношения.\n"
            f"{greet_line}"
            "- Уточнения: обычно от двух до пяти обменов, пока не ясны люди, фон и вопрос; не спеши с ready_for_spread=true.\n"
            "- В одном сообщении не больше одного короткого вопроса пользователю; не перечисляй несколько вопросов подряд.\n"
            "- Если нужно несколько уточнений, задавай их по очереди в разных сообщениях.\n"
            "- ready_for_spread=true только когда достаточно понятна ситуация или пользователь дал полный контекст одним длинным сообщением.\n"
            "- refuse_dialog только при явном тролле после предупреждений."
        )
    if spread_id == "ten_cards":
        return (
            "Режим: Кельтский крест.\n"
            f"{greet_line}"
            "- Уточнения: обычно от трёх до десяти обменов, пока не сложится картина ситуации.\n"
            "- В одном сообщении не больше одного короткого вопроса пользователю; не перечисляй несколько вопросов подряд.\n"
            "- Уточняй глубоко и конкретно: фокус проблемы, ключевой страх/риск, желаемый исход, ограничение по действиям.\n"
            "- Избегай поверхностных или формальных вопросов. Каждый вопрос должен реально менять точность расклада.\n"
            "- ready_for_spread=true только после явного согласия пользователя на запуск (да, давай, хочу, окей) после твоего предложения перейти к раскладу.\n"
            "- refuse_dialog только при явном тролле после предупреждений."
        )
    return (
        "Режим: общий. Веди себя как таролог, уточняй по минимуму. "
        f"{greet_line}"
        "В одном сообщении не больше одного короткого вопроса пользователю. "
        "ready_for_spread=true только когда вопрос к раскладу понятен, не на одно приветствие."
    )


@router.post("/tarologist-chat", response_model=TarotTarologistChatResponse)
async def tarot_tarologist_chat(
    payload: TarotTarologistChatRequest,
    db: AsyncSession = Depends(get_db),
) -> TarotTarologistChatResponse:
    """Чат с тарологом Григорием Астровым перед раскладом (без reading_id)."""
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    await _enforce_tarot_chat_rate_limit(user_id, "tarologist", limit=40, window_sec=600)
    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=422, detail="Сообщение пустое.")

    messages = list(payload.messages or [])
    messages.append({"role": "user", "content": user_message})
    if len(messages) > 20:
        messages = messages[-20:]

    spread_id = (payload.spread_id or "three_cards").strip().lower()
    spread_name = payload.spread_name or SPREADS.get(spread_id, {}).get("name", "расклад")
    deck_name = payload.deck_name or "колода"

    user_only = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    user_turns = len(user_only)

    history_lines = "\n".join(
        [f"{m.get('role')}: {m.get('content')}" for m in messages[-12:] if isinstance(m, dict)]
    )
    system_base = get_tarot_expert_system_prefix()
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    mode_block = _tarologist_mode_block(spread_id)
    min_auto = TAROLOGIST_MIN_USER_TURNS_FOR_AUTO.get(spread_id, 1)
    turn_rule = (
        f"Сейчас пользователь прислал сообщение номер {user_turns} в этом чате. "
        f"Не ставь ready_for_spread=true раньше минимума из {min_auto} сообщений пользователя, "
        "если только его вопрос к раскладу уже длинный и самодостаточный (примерно от 320 символов) "
        "или в конце явное согласие на расклад после твоего «Выполнить расклад?». "
        "Короткий, но ясный вопрос вроде «что мешает росту», «что дальше с работой» не требует длинной прелюдии.\n"
    )
    system = (
        f"{system_base}\n\n"
        "Ты Григорий Астров, опытный таролог в бытовом, спокойном тоне: тепло, но не сентиментально и не «психологически копающе».\n"
        f"Расклад: {spread_name}. Колода: {deck_name}.\n"
        f"Сейчас по серверу (для вопросов про время): {now_str}.\n\n"
        "Ты уточняешь формулировку вопроса к картам и рамки гадания, а не собираешь терапевтический портрет. "
        "Не используй язык боли и ран: избегай «что болит сильнее всего», «где ранит», «живого болезненного контекста» и похожего.\n\n"
        "Безопасность: не продвигай насилие, самоповреждение, нелегальные действия; не обсуждай интим с несовершеннолетними. "
        "Не задавай унизительных и лишне личных вопросов. На грубость отвечай спокойно, с границами, без ответной агрессии.\n\n"
        f"{mode_block}\n\n"
        f"{turn_rule}\n"
        "Не интерпретируй карты до выполнения расклада. Никогда не упоминай кнопки, вкладки или интерфейс приложения. "
        "Пиши живо и по-человечески: без канцелярита, без тяжёлых конструкций вроде «нужен сам расклад или ваше согласие». "
        "Не используй натянутые метафоры и абстракции вместо прямых вопросов («без тумана», «вектор», «прозрачная картина» и т.п.): говори так, как обычно говорит таролог в беседе.\n"
        "Поддержка не равна допросу: если вопрос уже звучит чётко, переходи к предложению расклада.\n"
        "Когда контекста достаточно, задай короткий вопрос ровно в такой формулировке: «Выполнить расклад?». "
        "ready_for_spread=true только если в последнем сообщении пользователя уже есть явное согласие на расклад (да, давай, хочу, окей) после твоего вопроса о переходе, "
        "или если одним длинным сообщением пользователь дал полный контекст и явно хочет гадание.\n\n"
        "Формат ответа: верни СТРОГО один JSON без markdown:\n"
        '{"reply":"текст на русском, 1-6 предложений","ready_for_spread":false,"refuse_dialog":false}\n'
        "Поля: reply (коротко, без перечня из нескольких вопросов по пунктам; если не уместно, одно предложение вопроса пользователю); ready_for_spread (true только при согласии пользователя или длинном явном запросе, см. выше); refuse_dialog (true только при отказе продолжать из-за троллинга; тогда ready_for_spread всегда false)."
    )
    prompt = (
        f"История диалога (последние реплики):\n{history_lines}\n\n"
        f"Новое сообщение пользователя: {user_message}\n\n"
        f"Это сообщение пользователя номер {user_turns} в этом чате.\n"
        "Сформируй JSON по правилам системы."
    )
    settings = get_settings()
    tarologist_model = (getattr(settings, "AI_TAROLOGIST_MODEL", None) or "gpt-4o").strip()
    interp_model = (getattr(settings, "AI_TAROT_INTERPRETATION_MODEL", None) or "").strip()
    model_chain: list[str | None] = [tarologist_model, None]
    if interp_model and interp_model not in {tarologist_model, ""}:
        model_chain.append(interp_model)

    raw: str | None = None
    last_exc: Exception | None = None
    for model_ov in model_chain:
        try:
            raw = await asyncio.wait_for(
                ai_client.generate_text(
                    prompt,
                    system_prompt=system,
                    max_tokens=420,
                    user_id=user_id,
                    profile_id=None,
                    feature_type="tarot_tarologist_chat",
                    model_override=model_ov,
                ),
                timeout=18.0,
            )
            if (raw or "").strip():
                break
            logger.warning("tarologist chat: empty reply from model %s, trying next", model_ov)
        except Exception as exc:
            last_exc = exc
            logger.warning("tarologist chat: model %s failed: %s", model_ov, exc)
    if not (raw or "").strip():
        if last_exc:
            logger.exception("tarologist chat: all models failed: %s", last_exc)
        return TarotTarologistChatResponse(
            response="Не удалось ответить. Попробуйте ещё раз чуть позже.",
            enough_info=False,
            refuse_to_continue=False,
        )
    parsed = _parse_json_object(raw or "")
    reply = str(parsed.get("reply") or "").strip()
    ready = bool(parsed.get("ready_for_spread"))
    refuse = bool(parsed.get("refuse_dialog"))

    if not reply:
        reply = (raw or "").strip()
        ready = False
        refuse = False
    if not reply:
        reply = (
            "Сформулируйте вопрос к картам своими словами: о чём хотите спросить колоду, и я подстрою расклад под тему."
        )

    unclear = any(x in reply.lower() for x in ("не понял", "не совсем понял", "не уловил"))
    if unclear:
        ready = False

    if _tarologist_user_message_is_greeting_only(user_message):
        ready = False
        refuse = False

    last_asst = _tarologist_last_assistant_message(messages)
    affirmative = _tarologist_user_message_is_affirmative(user_message)
    long_enough = len(user_message) >= 320
    min_auto = TAROLOGIST_MIN_USER_TURNS_FOR_AUTO.get(spread_id, 1)

    enough_info = bool(ready and not refuse)
    if enough_info and user_turns < min_auto and not long_enough:
        enough_info = False
    if enough_info and not long_enough and not affirmative:
        enough_info = False
    if spread_id == "ten_cards":
        enough_info = bool(
            not refuse
            and affirmative
            and user_turns >= min_auto
            and _tarologist_assistant_asked_spread_confirm(last_asst)
        )
        if user_turns < min_auto:
            enough_info = False
            ready = False
            if _tarologist_reply_asks_to_start_spread(reply):
                reply = _tarologist_ten_cards_deep_followup(user_turns)
            if "?" not in reply:
                reply = _tarologist_ten_cards_deep_followup(user_turns)
    if (
        affirmative
        and user_turns >= min_auto
        and _tarologist_assistant_asked_spread_confirm(last_asst)
        and not refuse
    ):
        enough_info = True

    return TarotTarologistChatResponse(
        response=reply,
        enough_info=enough_info,
        refuse_to_continue=refuse,
    )


@router.post("/chat", response_model=TarotChatResponse)
async def tarot_chat(
    payload: TarotChatRequest,
    db: AsyncSession = Depends(get_db),
) -> TarotChatResponse:
    user_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    await _enforce_tarot_chat_rate_limit(user_id, "reading", limit=50, window_sec=600)
    reading = (
        await db.execute(
            select(TarotReading).where(
                TarotReading.id == payload.reading_id, TarotReading.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    fallback_data: dict[str, Any] | None = None
    if not reading:
        cached = await cache_get_json(_chat_cache_key(user_id, payload.reading_id))
        fallback_data = cached if isinstance(cached, dict) else None
        if not fallback_data:
            raise HTTPException(status_code=404, detail="Расклад не найден.")
    user_message = (payload.message or "").strip()
    if not user_message:
        raise HTTPException(status_code=422, detail="Сообщение пустое.")

    chat_history = list(reading.chat_history or []) if reading else list(fallback_data.get("chat_history") or [])
    chat_history.append({"role": "user", "content": user_message})
    history_lines = "\n".join(
        [f"{m.get('role')}: {m.get('content')}" for m in chat_history[-12:] if isinstance(m, dict)]
    )
    base_question = reading.question if reading else str(fallback_data.get("question", ""))
    base_summary = (
        reading.summary
        if reading
        else str(fallback_data.get("summary") or fallback_data.get("overall", ""))
    )
    base_advice = reading.advice if reading else str(fallback_data.get("advice", ""))
    cards_payload = reading.cards if reading else list(fallback_data.get("cards") or [])
    cards_interp = reading.cards_interpretations if reading else []
    interp_by_pos: dict[int, dict[str, Any]] = {}
    if isinstance(cards_interp, list):
        for item in cards_interp:
            if not isinstance(item, dict):
                continue
            try:
                pos = int(item.get("position", -1))
            except (TypeError, ValueError):
                continue
            interp_by_pos[pos] = item
    cards_lines: list[str] = []
    if isinstance(cards_payload, list):
        for idx, c in enumerate(cards_payload):
            if not isinstance(c, dict):
                continue
            pos = idx
            name = str(c.get("card_name") or c.get("card_id") or f"Карта {idx + 1}").strip()
            position_name = str(c.get("position_name") or f"Позиция {idx + 1}").strip()
            is_reversed = bool(c.get("is_reversed"))
            interp = interp_by_pos.get(pos, {})
            interp_short = str(interp.get("interpretation") or "").strip()
            if len(interp_short) > 240:
                interp_short = interp_short[:240].rstrip() + "..."
            cards_lines.append(
                f"{idx + 1}) {name} | {position_name} | {'перевёрнутая' if is_reversed else 'прямая'}"
                + (f" | смысл: {interp_short}" if interp_short else "")
            )
    cards_context = "\n".join(cards_lines)
    prompt = (
        "Ты - опытный таролог. Пользователь получил расклад и задает уточнение.\n"
        f"Вопрос пользователя в раскладе: {base_question}\n"
        f"Итог расклада: {base_summary}\n"
        f"Карты расклада (обязательно опирайся на них):\n{cards_context}\n"
        f"История диалога:\n{history_lines}\n"
        f"Новый вопрос: {user_message}\n"
        "Ответь как таролог по этим картам и позициям, а не как общий психолог. "
        "Укажи минимум 3 конкретные карты из списка и свяжи их с вопросом. "
        "Ответ 5-7 предложений, предметно, без воды. Если чего-то не хватает, задай 1 встречный вопрос.\n"
        "Верни строго JSON: "
        '{"response":"...","updated_advice":"...","new_questions":["..."]}'
    )
    system_prompt = get_tarot_expert_system_prefix()
    try:
        profile_id_val = reading.profile_id if reading else None
        raw = await ai_client.generate_text(
            prompt,
            system_prompt=system_prompt,
            max_tokens=450,
            user_id=user_id,
            profile_id=profile_id_val,
            feature_type="tarot_followup_chat",
        )
        parsed = _parse_json_object(raw)
    except Exception as exc:
        logger.exception("tarot chat failed: %s", exc)
        parsed = {}

    response = (parsed.get("response") or "Сейчас важно сделать паузу и посмотреть на ситуацию спокойнее.").strip()
    updated_advice = (parsed.get("updated_advice") or base_advice or "").strip()
    new_questions = parsed.get("new_questions")
    if not isinstance(new_questions, list):
        new_questions = []
    new_questions = [str(x).strip() for x in new_questions if str(x).strip()]

    chat_history.append({"role": "assistant", "content": response})
    if reading:
        reading.chat_history = chat_history
        if updated_advice:
            reading.advice = updated_advice
        if new_questions:
            reading.follow_up_questions = new_questions
        await db.flush()
    else:
        fallback_data["chat_history"] = chat_history
        if updated_advice:
            fallback_data["advice"] = updated_advice
        if new_questions:
            fallback_data["follow_up_questions"] = new_questions
        try:
            await cache_set_json(
                _chat_cache_key(user_id, payload.reading_id),
                fallback_data,
                ttl_seconds=48 * 60 * 60,
            )
        except Exception:
            logger.exception("tarot chat fallback cache save failed")

    return TarotChatResponse(
        reading_id=reading.id if reading else payload.reading_id,
        response=response,
        updated_advice=(reading.advice if reading else str(fallback_data.get("advice", ""))) or "",
        new_questions=(reading.follow_up_questions if reading else (fallback_data.get("follow_up_questions") or [])) or [],
        chat_history=chat_history,
    )


@router.get("/history", response_model=TarotHistoryResponse)
async def tarot_history(
    init_data: str,
    profile_id: int | None = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> TarotHistoryResponse:
    user_id = get_telegram_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    page = max(1, page)
    limit = max(1, min(limit, 100))
    profile_id = sanitize_profile_id_for_db(profile_id)
    filters = [TarotReading.user_id == user_id]
    if profile_id is not None:
        filters.append(TarotReading.profile_id == profile_id)
    stmt = select(TarotReading).where(*filters)
    try:
        total_stmt = select(func.count()).select_from(TarotReading).where(*filters)
        total = int((await db.execute(total_stmt)).scalar() or 0)
        if total == 0:
            return TarotHistoryResponse(items=[], total=0, page=page, limit=limit)
        start = (page - 1) * limit
        rows = (
            await db.execute(
                stmt.order_by(TarotReading.created_at.desc()).offset(start).limit(limit)
            )
        ).scalars().all()
    except Exception as exc:
        logger.exception("tarot history query failed: %s", exc)
        return TarotHistoryResponse(items=[], total=0, page=page, limit=limit)
    out = []
    for r in rows:
        cards_preview = []
        for c in (r.cards or [])[:3]:
            if isinstance(c, dict):
                cards_preview.append(
                    {
                        "card_id": c.get("card_id"),
                        "card_name": c.get("card_name") or c.get("card_id"),
                        "is_reversed": bool(c.get("is_reversed")),
                    }
                )
        out.append(
            TarotHistoryItem(
                id=r.id,
                spread_code=r.spread_code,
                question=r.question or "",
                summary=(r.summary or "")[:280],
                cards_preview=cards_preview,
                created_at=r.created_at,
            )
        )
    return TarotHistoryResponse(items=out, total=total, page=page, limit=limit)


@router.get("/stats", response_model=TarotStatsResponse)
async def tarot_stats(
    init_data: str,
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> TarotStatsResponse:
    user_id = get_telegram_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(status_code=401, detail="Откройте приложение из Telegram.")
    profile_id = sanitize_profile_id_for_db(profile_id)
    cache_profile = profile_id if profile_id is not None else "all"
    cache_key = f"tarot:stats:{user_id}:{cache_profile}"
    try:
        cached = await cache_get_json(cache_key)
    except Exception:
        cached = None
    if isinstance(cached, dict) and cached:
        try:
            return TarotStatsResponse(**cached)
        except Exception:
            pass

    stmt = select(TarotReading.cards, TarotReading.created_at).where(TarotReading.user_id == user_id)
    if profile_id is not None:
        stmt = stmt.where(TarotReading.profile_id == profile_id)
    try:
        rows = (await db.execute(stmt)).all()
    except Exception as exc:
        logger.exception("tarot stats query failed: %s", exc)
        return TarotStatsResponse(
            total_readings=0,
            top_cards=[],
            reversed_ratio={"upright": 0, "reversed": 0},
            arcana_ratio={"major": 0, "minor": 0},
            recurring_cards=[],
        )

    cards_counter: Counter[str] = Counter()
    reversed_count = 0
    upright_count = 0
    major_count = 0
    minor_count = 0
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    monthly_counter: Counter[str] = Counter()

    for cards, created_at in rows:
        created_at_value = created_at
        if isinstance(created_at_value, datetime) and created_at_value.tzinfo is None:
            created_at_value = created_at_value.replace(tzinfo=timezone.utc)
        for card in cards or []:
            if not isinstance(card, dict):
                continue
            cid = str(card.get("card_id") or "").strip()
            if not cid:
                continue
            cards_counter[cid] += 1
            if card.get("is_reversed"):
                reversed_count += 1
            else:
                upright_count += 1
            if _is_major(cid):
                major_count += 1
            else:
                minor_count += 1
            if isinstance(created_at_value, datetime) and created_at_value >= month_ago:
                monthly_counter[cid] += 1

    top_cards = [
        {"card_id": cid, "count": count} for cid, count in cards_counter.most_common(5)
    ]
    recurring_cards = [
        {"card_id": cid, "count": count}
        for cid, count in monthly_counter.items()
        if count >= 3
    ]
    recurring_cards.sort(key=lambda x: x["count"], reverse=True)
    recurring_cards = recurring_cards[:10]

    response_data = {
        "total_readings": len(rows),
        "top_cards": top_cards,
        "reversed_ratio": {"upright": upright_count, "reversed": reversed_count},
        "arcana_ratio": {"major": major_count, "minor": minor_count},
        "recurring_cards": recurring_cards,
    }
    try:
        await cache_set_json(cache_key, response_data, ttl_seconds=120)
    except Exception:
        logger.debug("tarot stats cache set failed for %s", cache_key)

    return TarotStatsResponse(
        total_readings=response_data["total_readings"],
        top_cards=top_cards,
        reversed_ratio=response_data["reversed_ratio"],
        arcana_ratio=response_data["arcana_ratio"],
        recurring_cards=recurring_cards,
    )


@router.get("/recurring")
async def tarot_recurring(
    init_data: str,
    profile_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stats = await tarot_stats(init_data=init_data, profile_id=profile_id, db=db)
    return {"items": stats.recurring_cards}
