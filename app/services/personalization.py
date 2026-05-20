"""Personalization helpers: name style, age segment, tone hints."""

from datetime import date


_MALE_NAME_CANONICAL_MAP = {
    "миша": "Михаил",
    "мишка": "Михаил",
    "михуил": "Михаил",
    "саша": "Александр",
    "саня": "Александр",
    "шура": "Александр",
    "дима": "Дмитрий",
    "димон": "Дмитрий",
    "лёша": "Алексей",
    "леша": "Алексей",
    "алеша": "Алексей",
    "женя": "Евгений",
    "женек": "Евгений",
    "сережа": "Сергей",
    "серёжа": "Сергей",
    "юра": "Юрий",
    "паша": "Павел",
}

_FEMALE_NAME_CANONICAL_MAP = {
    "саша": "Александра",
    "саня": "Александра",
    "шура": "Александра",
    "аня": "Анна",
    "анюта": "Анна",
    "катя": "Екатерина",
    "катька": "Екатерина",
    "женя": "Евгения",
    "оля": "Ольга",
    "оленька": "Ольга",
    "юля": "Юлия",
    "юлечка": "Юлия",
    "маша": "Мария",
    "маруся": "Мария",
    "наташа": "Наталья",
    "таня": "Татьяна",
    "света": "Светлана",
}

_NEUTRAL_NAME_CANONICAL_MAP = {
    "миша": "Михаил",
    "мишка": "Михаил",
    "дима": "Дмитрий",
    "леша": "Алексей",
    "лёша": "Алексей",
    "алеша": "Алексей",
    "аня": "Анна",
    "анюта": "Анна",
    "катя": "Екатерина",
    "катька": "Екатерина",
    "оля": "Ольга",
    "юля": "Юлия",
    "юлечка": "Юлия",
}


def normalize_profile_name(name: str | None) -> str:
    """Return short clean profile name (first token)."""
    raw = (name or "").strip()
    if not raw:
        return ""
    first = raw.split()[0].strip()
    if not first:
        return ""
    return first[:1].upper() + first[1:]


def canonical_form_name(name: str | None, gender: str | None = None) -> str:
    """Map nickname to formal form (e.g. Миша -> Михаил), with gender-aware aliases."""
    short = normalize_profile_name(name)
    if not short:
        return ""
    key = short.lower()
    g = (gender or "").strip().lower()
    if g in {"m", "male", "м"}:
        return _MALE_NAME_CANONICAL_MAP.get(key) or _NEUTRAL_NAME_CANONICAL_MAP.get(key) or short
    if g in {"f", "female", "ж"}:
        return _FEMALE_NAME_CANONICAL_MAP.get(key) or _NEUTRAL_NAME_CANONICAL_MAP.get(key) or short
    return _NEUTRAL_NAME_CANONICAL_MAP.get(key) or short


def age_from_birth_date(birth_date_value: date | str | None) -> int | None:
    """Calculate age in years from date or YYYY-MM-DD string."""
    if birth_date_value is None:
        return None
    if isinstance(birth_date_value, date):
        born = birth_date_value
    else:
        s = str(birth_date_value).strip()
        if not s:
            return None
        try:
            parts = s.split("-")
            born = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, TypeError, IndexError):
            return None
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 0 or age > 120:
        return None
    return age


def age_style_instruction(age: int | None) -> str:
    """Tone/style guidance by age segment."""
    if age is None:
        return "Тон: дружелюбный, ясный, без канцелярита."
    if age < 18:
        return (
            "Тон: поддерживающий и бережный. "
            "Контекст: учеба, друзья, развитие навыков, хобби. "
            "Не делать акцент на работе и карьерной гонке."
        )
    if 18 <= age <= 32:
        return (
            "Тон: живой и современный, можно 1-2 актуальных разговорных выражения без сленг-перегиба. "
            "Контекст: рост, выбор направлений, отношения, первые серьезные проекты."
        )
    if 32 <= age <= 45:
        return (
            "Тон: уверенный, практичный. "
            "Контекст: достижения, эффективность, баланс нагрузки, управленческие решения."
        )
    return (
        "Тон: уважительный и зрелый, без фамильярности. "
        "Контекст: опыт, устойчивые решения, здоровье, качество жизни и долгие циклы."
    )


def personalized_display_name(name: str | None, age: int | None, gender: str | None = None) -> str:
    """Preferred address form for generated texts."""
    formal = canonical_form_name(name, gender=gender)
    if not formal:
        return "Вы"
    # Keep addressing natural; respectful tone is handled by phrasing, not honorific prefixes.
    return formal


def naming_style_instruction(raw_name: str | None, canonical_name: str, display_name: str) -> str:
    """Instruction for LLM: how to use and inflect name naturally."""
    source = normalize_profile_name(raw_name)
    if not canonical_name:
        return "Если имя неизвестно - обращайся нейтрально на «вы»."
    if source and source.lower() != canonical_name.lower():
        return (
            f"Имя пользователя может звучать как «{source}», каноническая форма - «{canonical_name}». "
            f"Обращайся как «{display_name}», сохраняй естественное русское склонение имени."
        )
    return f"Обращайся как «{display_name}», сохраняй естественное русское склонение имени."
