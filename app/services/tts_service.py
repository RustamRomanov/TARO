"""Вспомогательные функции для TTS: словарь ударений и правки произношения."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PR_FIXES: dict[str, Any] | None = None

# Сокращения «N-м» (в N-м доме): TTS часто читает как «один-м». Нужна предложная форма.
_ORDINAL_TO_PREP_M: dict[str, str] = {
    "1": "первом",
    "2": "втором",
    "3": "третьем",
    "4": "четвёртом",
    "5": "пятом",
    "6": "шестом",
    "7": "седьмом",
    "8": "восьмом",
    "9": "девятом",
    "10": "десятом",
    "11": "одиннадцатом",
    "12": "двенадцатом",
}

_ORDINAL_M_PATTERN = re.compile(r"(?<!\d)(\d{1,2})-м(?!\d)", re.IGNORECASE)


def load_pronunciation_fixes() -> dict[str, Any]:
    """Загружает словарь замен из JSON (один раз при первом вызове)."""
    global _PR_FIXES
    if _PR_FIXES is None:
        json_path = Path(__file__).resolve().parent.parent / "data" / "pronunciation_fixes.json"
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                _PR_FIXES = json.load(f)
        else:
            _PR_FIXES = {}
    return _PR_FIXES


def _flatten_fixes(fixes: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for category in fixes.values():
        if not isinstance(category, dict):
            continue
        for wrong, correct in category.items():
            if isinstance(wrong, str) and isinstance(correct, str) and wrong:
                pairs.append((wrong, correct))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def _match_case(source: str, template: str) -> str:
    """Переносит регистр с найденного фрагмента на эталонную форму (с ударением)."""
    if not template:
        return template
    if source.isupper():
        return template.upper()
    if source[0].isupper():
        return template[0].upper() + template[1:]
    return template[0].lower() + template[1:] if len(template) > 1 else template.lower()


def _expand_ordinal_m_abbrev(text: str) -> str:
    """Подмена «1-м» на «первом» и т.д. для фраз вроде «в вашем 1-м доме»."""

    def repl(m: re.Match[str]) -> str:
        num = m.group(1)
        if num.startswith("0") and len(num) > 1:
            num = str(int(num, 10))
        word = _ORDINAL_TO_PREP_M.get(num)
        if not word:
            return m.group(0)
        return _match_case(m.group(0), word)

    return _ORDINAL_M_PATTERN.sub(repl, text)


def fix_pronunciation(text: str) -> str:
    """Словарь ударений и подстановки для TTS (в т.ч. сокращения порядковых с числом)."""
    text = _expand_ordinal_m_abbrev(text)
    fixes = load_pronunciation_fixes()
    if not fixes:
        return text
    pairs = _flatten_fixes(fixes)
    total_subs = 0
    for wrong, correct in pairs:
        if wrong == correct:
            continue
        pattern = re.escape(wrong)

        def make_repl(correct_inner: str = correct):
            def repl(m: re.Match[str]) -> str:
                nonlocal total_subs
                total_subs += 1
                return _match_case(m.group(0), correct_inner)

            return repl

        text, _ = re.subn(pattern, make_repl(), text, flags=re.IGNORECASE)
    if total_subs > 0:
        logger.debug("TTS pronunciation fixes applied: %s replacement(s)", total_subs)
    return text
