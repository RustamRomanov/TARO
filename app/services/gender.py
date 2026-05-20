"""Определение пола по имени и формирование подсказки для ИИ."""


def infer_gender_from_name(name: str) -> str | None:
    """
    По имени определяет пол для сохранения в профиле.
    Учитывает кириллицу и латиницу (например Karina, Анна).
    Возвращает "m", "f" или None (неочевидное имя).
    """
    n = (name or "").strip().lower().replace("ё", "е")
    if not n or len(n) < 2:
        return None
    # Иногда в поле имени приходит "Имя Фамилия", для эвристики берём первое слово.
    n = n.split()[0].strip()
    if not n:
        return None

    # Явные словари: снижают ошибки на мужских именах на "-а/-я" (Никита, Илья, Сережа и т.п.).
    male_strong = {
        "сережа", "серега", "сергеи", "сергей",
        "никита", "илья", "фома", "кузьма", "лука", "савва", "данила",
        "юра", "паша", "миша", "гриша", "леша", "слава",
    }
    female_strong = {
        "анна", "мария", "елена", "ольга", "наталья", "евгения",
        "евангелина", "карина", "алена", "юлия", "ирина", "софия",
        "дарья", "оксана", "татьяна",
    }
    # Амбивалентные формы: лучше не угадывать.
    ambiguous = {"женя", "саша", "валя"}
    if n in ambiguous:
        return None
    if n in male_strong:
        return "m"
    if n in female_strong:
        return "f"

    last = n[-1]
    # Женские окончания: кириллица (а, я, ...) и латиница (a в конце).
    male_exceptions_cyr = ("никита", "илья", "фома", "кузьма", "лука", "савва", "данила", "сережа", "серега")
    fem_cyrillic_endings = ("а", "я", "ья", "ия", "ея")
    fem_latin_end = last == "a" and ord(last) < 128  # Latin 'a' (Karina, Anna, Maria)
    if n.endswith(fem_cyrillic_endings) and not n.endswith(male_exceptions_cyr):
        return "f"
    if fem_latin_end and not n.endswith(("nikita", "ilya", "foma", "kuzma", "luka", "savva", "danila", "serezha", "serega")):
        return "f"
    # Мужские окончания (кириллица и латиница: y, о и т.д.)
    male_cyrillic = ("й", "ь", "л", "н", "р", "м", "с", "в", "к", "т", "д", "г")
    if n.endswith(male_cyrillic) and len(n) > 2:
        return "m"
    if last in ("n", "r", "m", "s", "v", "k", "t", "d") and len(n) > 2:  # Latin male endings (Rustam -> m)
        return "m"
    # Gregory, Harry, Barry - латиница, окончание на y
    if last == "y" and len(n) > 4 and ord(last) < 128 and n not in ("mary", "betty", "sally", "nancy", "abby"):
        return "m"
    # Известные мужские имена по началу (username и т.п.)
    if n.startswith(("greg", "harry", "barry", "ronald", "donald", "randy")):
        return "m"
    return None


def gender_hint_for_prompt(gender: str | None, name: str | None = None) -> str:
    """
    Текст для промпта ИИ: как обращаться к пользователю (род).
    Если gender задан - по нему; иначе по имени через infer_gender_from_name.
    """
    if gender and (g := gender.strip().lower()) in ("m", "f", "м", "ж", "male", "female"):
        if g in ("m", "м", "male"):
            return "Обращайся к пользователю в мужском роде (он, его)."
        return "Обращайся к пользователю в женском роде (она, её)."
    if name:
        inferred = infer_gender_from_name(name)
        if inferred == "m":
            return "Обращайся к пользователю в мужском роде (он, его)."
        if inferred == "f":
            return "Обращайся к пользователю в женском роде (она, её)."
    return "Если пол непонятен, обращайся нейтрально."


async def infer_gender_by_ai(ai_client, name: str) -> str | None:
    """Один запрос к ИИ: по имени определить пол. Возвращает 'm', 'f' или None."""
    if not (name or "").strip():
        return None
    prompt = (
        f'По имени «{(name or "").strip()}» определи пол человека. '
        "Ответь строго одной буквой: m (мужской) или f (женский). Без пояснений."
    )
    try:
        raw = (await ai_client.generate_text(prompt, system_prompt=None, max_tokens=10)).strip().lower()
        if raw in ("m", "f"):
            return raw
        if raw.startswith("m") or "муж" in raw:
            return "m"
        if raw.startswith("f") or "жен" in raw:
            return "f"
    except Exception:
        pass
    return None


async def infer_gender_from_text_by_ai(ai_client, question_or_text: str) -> str | None:
    """По формулировке вопроса/текста определить, от лица мужчины или женщины. Возвращает 'm', 'f' или None."""
    if not (question_or_text or "").strip() or len((question_or_text or "").strip()) < 10:
        return None
    prompt = (
        "По формулировке текста определи, задан ли он от лица мужчины или женщины. "
        "Учитывай род (я хочу, я хотела, меня беспокоит и т.п.). "
        "Ответь строго одной буквой: m (мужской) или f (женский). Без пояснений."
        f"\n\nТекст: {(question_or_text or '')[:800]}"
    )
    try:
        raw = (await ai_client.generate_text(prompt, system_prompt=None, max_tokens=10)).strip().lower()
        if raw in ("m", "f"):
            return raw
        if raw.startswith("m") or "муж" in raw:
            return "m"
        if raw.startswith("f") or "жен" in raw:
            return "f"
    except Exception:
        pass
    return None
