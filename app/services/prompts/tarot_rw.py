"""
Промпты таро в духе Rider-Waite-Smith и тип карты для /api/tarot/draw и /api/tarot/draw-batch.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

# --- Позиции раскладов (если с фронта не пришёл position_name) -----------------

SPREAD_POSITIONS: dict[int, list[str]] = {
    1: ["Позиция расклада"],
    3: ["Прошлое", "Настоящее", "Итог"],
    5: ["Ситуация", "Препятствие", "Совет", "Результат", "Итог"],
    6: ["Она", "Он", "Взаимодействие", "Объединяющее", "Разъединяющее", "Итог"],
    7: ["Очаг", "Мысли", "Чувства", "Реальность", "Надежды", "Влияние", "Итог"],
    10: [
        "Ситуация",
        "Препятствие",
        "Основа",
        "Недавнее прошлое",
        "Возможное",
        "Ближайшее будущее",
        "Ваша роль",
        "Роль других",
        "Надежды и страхи",
        "Итог",
    ],
}


def resolve_spread_position_index(position: int | None, total_cards: int) -> int:
    """Индекс позиции 0..t-1; клиент шлёт чаще 1-based (1..t), реже 0-based."""
    if position is None:
        return 0
    p = int(position)
    t = max(1, int(total_cards))
    if 1 <= p <= t:
        return p - 1
    if 0 <= p < t:
        return p
    return max(0, min(t - 1, p))


def get_position_name(position_index: int, total_cards: int) -> str:
    """Название позиции по 0-based индексу и числу карт в раскладе."""
    total = max(1, int(total_cards))
    idx = max(0, int(position_index))
    positions = SPREAD_POSITIONS.get(total)
    if positions and idx < len(positions):
        return positions[idx]
    return f"Позиция {idx + 1}"


def get_reversed_suffix(is_reversed: bool) -> str:
    if is_reversed:
        return " (перевёрнутая)"
    return ""


def _coerce_attr(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# --- Тип карты -----------------------------------------------------------------

_MAJOR_KEYWORDS_RU = (
    "Шут",
    "Маг",
    "Жрица",
    "Верховная",
    "Императрица",
    "Император",
    "Иерофант",
    "Влюбленные",
    "Колесница",
    "Сила",
    "Отшельник",
    "Колесо",
    "Справедливость",
    "Повешенный",
    "Смерть",
    "Умеренность",
    "Дьявол",
    "Башня",
    "Звезда",
    "Луна",
    "Солнце",
    "Суд",
    "Мир",
    "Дурак",
)

_COURT_KEYWORDS_RU = ("Паж", "Рыцарь", "Король", "Королева", "Принцесса", "Принц")

# Фрагменты английских названий (колоды с подписями на EN)
_MAJOR_TOKENS_EN = (
    "the fool",
    "the magician",
    "the high priestess",
    "the empress",
    "the emperor",
    "the hierophant",
    "the lovers",
    "the chariot",
    "strength",
    "the hermit",
    "wheel of fortune",
    "justice",
    "the hanged man",
    "death",
    "temperance",
    "the devil",
    "the tower",
    "the star",
    "the moon",
    "the sun",
    "judgement",
    "the world",
)


def get_tarot_card_type(card_name: str, card_id: str | None = None) -> str:
    """
    «Старший Аркан», «Придворный Аркан» или «Младший Аркан».
    Учитывает card_id вида 0-78 и префиксы major/minor в строке.
    """
    name = (card_name or "").strip()
    cid = (card_id or "").strip()
    cidl = cid.lower()

    if "major" in cidl or re.search(r"-major-", cidl):
        return "Старший Аркан"

    mnum = re.match(r"^(\d+)", cid)
    if mnum:
        idx = int(mnum.group(1))
        if 0 <= idx <= 21:
            return "Старший Аркан"
        if 22 <= idx <= 77:
            rank_in_suit = (idx - 22) % 14 + 1  # 1 Ace .. 14 King
            if rank_in_suit >= 11:
                return "Придворный Аркан"
            return "Младший Аркан"

    for kw in _COURT_KEYWORDS_RU:
        if kw in name:
            return "Придворный Аркан"

    nl = name.lower()
    if re.search(r"\b(page|knight|queen|king|knave)\s+of\b", nl):
        return "Придворный Аркан"
    if re.search(r"\b(page|knight|queen|king)\b", nl) and any(s in nl for s in ("wand", "cup", "swor", "pent", "disc", "coin", "candle", "potion", "needle", "present")):
        return "Придворный Аркан"

    for kw in _MAJOR_KEYWORDS_RU:
        if kw in name:
            return "Старший Аркан"

    for tok in _MAJOR_TOKENS_EN:
        if tok in nl:
            return "Старший Аркан"

    return "Младший Аркан"


# --- /api/tarot/draw: одна карта ------------------------------------------------

TAROT_SINGLE_CARD_SYSTEM = (
    "Ты — опытный таролог, следующий классической школе Райдера-Уэйта. "
    "В запросе пользователя заданы явные правила по типу карты (Старший, Придворный, Младший) и по перевёрнутости: следуй им буквально. "
    "Русский язык, без markdown (* и #), без перечислений «во-первых», «во-вторых». "
    "Обращайся на «ты». Не используй длинное тире (символ «длинное тире»): вместо него двоеточие, запятая или дефис."
)

TAROT_REVERSED_RULES = """4. Если карта перевёрнутая:
   - Для Старших Арканов: энергия карты заблокирована, искажена или проявляется в теневом аспекте
   - Для Придворных: человек проявляет свои негативные черты или его влияние направлено против тебя
   - Для Младших: ситуация идёт не так, есть препятствия, задержки или скрытые проблемы
   - В тексте интерпретации явно отметь, что карта перевёрнутая, и покажи, как это меняет смысл

"""

# Расклады draw-batch: единые правила для поля interpretation по каждой карте (в т.ч. 5, 7, 10 карт).
TAROT_BATCH_PER_CARD_INTERPRETATION_RULES = """При интерпретации каждой карты строго следуй полю card_type из списка «Карты»:
- Старший Аркан: описывай личность, урок или глубинный смысл, архетип; какая часть личности пользователя или какой человек в его жизни соответствует этому Аркану.
- Придворный Аркан: описывай человека (характер, роль, возраст) или черту личности пользователя; насколько человек влиятелен, активен, зрел или начинающий.
- Младший Аркан (числовой, от Туза до Десятки): описывай ситуацию, событие, динамику, обстоятельства, эмоциональный фон; не описывай человека.
Если карта перевёрнутая: явно отметь это в тексте интерпретации и учитывай теневой аспект - для Старшего энергия заблокирована, искажена или в теневом аспекте; для Придворного негативные черты или влияние против тебя; для Младшего ситуация идёт не так, препятствия, задержки или скрытые проблемы."""

TAROT_SINGLE_CARD_USER = """Перед тобой карта Таро:
- Название: {card_display_name}
- Тип карты: {card_type} (одно из: «Старший Аркан», «Придворный Аркан», «Младший Аркан»)
- Позиция в раскладе: {position_name}
- Вопрос пользователя: {question}
- На карте изображено: {visual_description}

**Правила интерпретации:**
1. Если карта — **Старший Аркан**: опиши, какую архетипическую личность, судьбоносный урок или глубинную жизненную силу она представляет. Сделай акцент на том, какая часть личности пользователя или какой человек в его жизни соответствует этому Аркану.

2. Если карта — **Придворный Аркан** (Паж, Рыцарь, Король, Королева): опиши, какого человека (его характер, возраст, роль) или какую черту личности самого пользователя эта карта символизирует. Укажи, является ли этот человек влиятельным, активным, зрелым или начинающим.

3. Если карта — **Младший Аркан** (числовой, от Туза до Десятки): опиши **ситуацию, событие или динамику**, которая сейчас происходит. Не описывай человека — описывай процесс, обстоятельства, течение дел, эмоциональный фон, вызов или возможность.

{reversed_rules}
**Стиль ответа:**
- 3–5 предложений
- Говори на русском языке, плавно, без маркдауна и без перечисления «во-первых»/«во-вторых»
- Используй мягкий, но уверенный тон
- Обращайся к пользователю на «ты»
- Если уместно, свяжи значение карты с вопросом пользователя
- Если «На карте изображено» пустое или «отсутствует», не выдумывай предметы на карте; толкуй архетип по названию и типу. Если описание есть, не добавляй свечи, музыку, танцы и т.д., если их нет в этом тексте.
- Не используй слово «визуал» в тексте для пользователя, говори естественно: «на карте изображено», «в изображении карты», «по образу карты».

**Твоя интерпретация:**"""


def build_tarot_single_card_user_prompt(
    *,
    card_name: str,
    card_type: str,
    position_name: str,
    question: str,
    visual_description: str,
    is_reversed: bool = False,
) -> str:
    base = card_name or "карта"
    return TAROT_SINGLE_CARD_USER.format(
        card_display_name=base + get_reversed_suffix(is_reversed),
        card_type=card_type,
        position_name=position_name or "общая позиция",
        question=question or "общая тема",
        visual_description=visual_description or "отсутствует",
        reversed_rules=TAROT_REVERSED_RULES if is_reversed else "",
    )


# --- Итог расклада (draw-batch: поле overall и связный синтез) ----------------

TAROT_SUMMARY_OVERALL_RULES = """**Правила синтеза итога (поля summary и overall):**

1. Проанализируй, как взаимодействуют между собой карты. Обрати внимание на:
   - Преобладание Старших Арканов (глубинные жизненные темы, судьбоносные уроки)
   - Придворные Арканы (ключевые люди в ситуации, роли)
   - Младшие Арканы (конкретные события, динамика, процессы)
   - Перевёрнутые карты ослабляют или искажают прямое значение: учитывай это в синтезе

2. В итоге опиши:
   - Общий вектор ситуации (куда всё движется)
   - Главный урок или вызов
   - Что будет, если пользователь последует совету карт
   - Короткую рекомендацию

**Стиль итога:**
- В summary: 1–2 короткие связные фразы
- В overall: 4–7 предложений, связно, без маркдауна
- Не перечисляй карты по отдельности в overall, синтезируй их в единую картину
- Обращайся к пользователю на «ты»
- Заверши коротким советом или вопросом для размышления
- Не используй длинное тире в тексте для пользователя"""

TAROT_SUMMARY_PROMPT = """Ты — опытный таролог, следующий классической школе Райдера-Уэйта.

Пользователь задал вопрос:
{question}

Расклад состоит из следующих карт:
{cards_summary}

**Правила синтеза итога:**

1. Проанализируй, как взаимодействуют между собой карты. Обрати внимание на:
   - Преобладание Старших Арканов (глубинные жизненные темы, судьбоносные уроки)
   - Придворные Арканы (ключевые люди в ситуации, роли)
   - Младшие Арканы (конкретные события, динамика, процессы)

2. В итоге опиши:
   - Общий вектор ситуации (куда всё движется)
   - Главный урок или вызов
   - Что будет, если пользователь последует совету карт
   - Короткую рекомендацию

**Стиль ответа:**
- 4–7 предложений
- Говори на русском языке, связно, без маркдауна
- Не перечисляй карты по отдельности, синтезируй их в единую картину
- Обращайся к пользователю на «ты»
- Заверши коротким советом или вопросом для размышления

**Твой итог расклада:**"""


def build_tarot_summary_prompt(*, question: str, cards_summary: str) -> str:
    return TAROT_SUMMARY_PROMPT.format(
        question=question or "общая тема",
        cards_summary=(cards_summary or "").strip() or "карты не переданы",
    )


def build_tarot_cards_summary_lines(
    *,
    cards: list[tuple[str, str, str]],
) -> str:
    """
    cards: список (название, тип, позиция) в порядке расклада.
    """
    lines: list[str] = []
    for name, ctype, pos in cards:
        lines.append(f"«{name}» ({ctype}) — Позиция: {pos}")
    return "\n".join(lines)


def format_cards_for_summary(cards: Sequence[Any]) -> str:
    """Строки для TAROT_SUMMARY_PROMPT: объекты с полями card_name, position_name, interpretation, card_id (опц.)."""
    lines: list[str] = []
    for i, card in enumerate(cards):
        name = str(_coerce_attr(card, "card_name", "") or "").strip() or "Карта"
        cid = _coerce_attr(card, "card_id", None)
        cid_s = str(cid).strip() if cid else None
        ctype = get_tarot_card_type(name, cid_s)
        pos = str(_coerce_attr(card, "position_name", "") or "").strip() or f"Позиция {i + 1}"
        interp = str(_coerce_attr(card, "interpretation", "") or "").strip()
        suffix = ""
        if bool(_coerce_attr(card, "is_reversed", False)):
            suffix = " (перевёрнутая)"
        line = f"{name}{suffix} ({ctype}) — {pos}"
        if interp:
            line = f"{line}: {interp}"
        lines.append(line)
    return "\n".join(lines)
