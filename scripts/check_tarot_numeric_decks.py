#!/usr/bin/env python3
"""
Проверка колод Таро с числовыми id файлов 0–77 (префикс «00-», «22-», … в имени).

1) По папкам в frontend/src/assets/taro: ровно 78 карт с индексами 0–77, без дыр и дубликатов
   (исключая рубашку и «колоду», регистронезависимо).

2) Опционально --json: в tarot_card_descriptions.json для deck_id с ключами «NN-...» извлекает
   подпись вида «TWO OF CUPS», IV OF PRESENTS и сверяет ранг и масть с ожидаемыми по номеру в ключе
   (не по переименованию в UI). Известные коллизии файла и гравюры: флаг --allow-known-mismatches.

Запуск из корня репозитория:
  python scripts/check_tarot_numeric_decks.py
  python scripts/check_tarot_numeric_decks.py --json app/data/tarot_card_descriptions.json
  python scripts/check_tarot_numeric_decks.py --json app/data/tarot_card_descriptions.json --allow-known-mismatches
  python scripts/check_tarot_numeric_decks.py --deck oriens_animal
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARO_ROOT = ROOT / "frontend" / "src" / "assets" / "taro"

# Имя папки (как в файловой системе) -> deck_id в tarotDecks.js
FOLDER_TO_DECK_ID: dict[str, str] = {
    "the dark mansion tarot": "dark_mansion",
    "the nightmare before christmas tarot": "nightmare_christmas",
    "oriens animal tarot": "oriens_animal",
    "trionfi della luna": "trionfi_luna",
}

# Зеркало DECK_DECIMAL_ID_INDEX_FIX в tarotCardNamesRu.js (stem нижний регистр без расширения)
# Переопределения для UI см. frontend/src/data/tarotCardNamesRu.js (для этого скрипта не используются:
# сверка JSON идёт по номеру в имени файла и подписи на гравюре).

# Индексы, которых нет на диске по замыслу издателя (остальные 0–77 должны быть согласованы).
SKIP_INDEX_ON_DISK: dict[str, frozenset[int]] = {
    "nightmare_christmas": frozenset({67}),
}

CARD_EXT = {".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG", ".WEBP"}

NUM_PREFIX_RE = re.compile(r"^(\d{1,2})-")
# Подпись на гравюре: FOUR OF PENTACLES, IV OF PRESENTS, «NINE OF CUPS»
LABEL_RE = re.compile(
    r"(?:«|\")?\s*([IVXLC]+|[A-Z]{2,20})\s+OF\s+([A-Z]{2,20})\s*(?:»|\")?",
    re.IGNORECASE,
)

WORD_RANK: dict[str, int] = {
    "ACE": 1,
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "PAGE": 11,
    "KNIGHT": 12,
    "QUEEN": 13,
    "KING": 14,
}

ROMAN_RANK: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
}

# Синонимы масти на гравюре -> нормализованная масть RWS
SUIT_ALIASES: dict[str, str] = {
    "WANDS": "wands",
    "BATS": "wands",
    "CANDLES": "wands",
    "CUPS": "cups",
    "CHALICES": "cups",
    "POTIONS": "cups",
    "SWORDS": "swords",
    "NEEDLES": "swords",
    "PENTACLES": "pentacles",
    "COINS": "pentacles",
    "DISKS": "pentacles",
    "DISCS": "pentacles",
    "PRESENTS": "pentacles",
    "DANARI": "pentacles",
}


def is_skipped_file(stem: str) -> bool:
    lower = stem.lower()
    return "рубаш" in lower or "колода" in lower


def stem_index(stem: str) -> int | None:
    m = NUM_PREFIX_RE.match(stem)
    if not m:
        return None
    return int(m.group(1))


def expected_minor(index: int) -> tuple[int, str] | None:
    if index <= 21:
        return None
    rel = index - 22
    suit_i = rel // 14
    rank = rel % 14 + 1
    suits = ("wands", "cups", "swords", "pentacles")
    if suit_i > 3:
        return None
    return rank, suits[suit_i]


def normalize_suit_token(raw: str) -> str | None:
    u = raw.upper().strip()
    return SUIT_ALIASES.get(u)


def parse_rank_token(raw: str) -> int | None:
    u = raw.upper().strip()
    if u in WORD_RANK:
        return WORD_RANK[u]
    if u in ROMAN_RANK:
        return ROMAN_RANK[u]
    return None


def last_card_label(description: str) -> tuple[int, str] | None:
    """Последнее совпадение «X OF Y» в тексте (часто итоговая подпись карты)."""
    if not description or description.strip() in ("{}", ""):
        return None
    matches = list(LABEL_RE.finditer(description))
    if not matches:
        return None
    m = matches[-1]
    rank = parse_rank_token(m.group(1))
    suit = normalize_suit_token(m.group(2))
    if rank is None or suit is None:
        return None
    return rank, suit


def collect_numeric_deck_files(deck_folder: Path) -> tuple[list[str], dict[int, str]]:
    """Список имён файлов-карт и отображение индекс -> stem (первый при дубликате)."""
    by_index: dict[int, str] = {}
    files: list[str] = []
    for p in sorted(deck_folder.iterdir()):
        if not p.is_file():
            continue
        if p.suffix not in CARD_EXT:
            continue
        stem = p.stem
        if is_skipped_file(stem):
            continue
        idx = stem_index(stem)
        if idx is None:
            continue
        files.append(p.name)
        if idx not in by_index:
            by_index[idx] = stem
    return files, by_index


def verify_file_indices(deck_id: str, by_index: dict[int, str]) -> list[str]:
    errors: list[str] = []
    expected = set(range(78)) - set(SKIP_INDEX_ON_DISK.get(deck_id, frozenset()))
    got = set(by_index.keys())
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    if missing:
        errors.append(f"  нет индексов: {missing}")
    if extra:
        errors.append(f"  лишние индексы: {extra}")
    return errors


def verify_no_duplicate_prefixes(deck_folder: Path, deck_id: str) -> list[str]:
    errors: list[str] = []
    counts: dict[int, list[str]] = {}
    for p in deck_folder.iterdir():
        if not p.is_file() or p.suffix not in CARD_EXT:
            continue
        if is_skipped_file(p.stem):
            continue
        idx = stem_index(p.stem)
        if idx is None:
            continue
        counts.setdefault(idx, []).append(p.name)
    for idx, names in sorted(counts.items()):
        if len(names) > 1:
            errors.append(f"  индекс {idx}: несколько файлов {names}")
    return errors


# Расхождение номера в имени файла и ранга на гравюре, уже учтённое в UI (оставить до правки JSON).
KNOWN_LABEL_VS_NUMBER: frozenset[tuple[str, str]] = frozenset({("nightmare_christmas", "72-Pentacles9")})


def verify_json_labels(
    data: dict[str, object],
    deck_filter: str | None,
    *,
    allow_known: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    num_key_re = re.compile(r"^(\d{1,2})-")

    for deck_id, section in data.items():
        if deck_filter and deck_id != deck_filter:
            continue
        if not isinstance(section, dict):
            continue
        numeric_keys = [k for k in section if isinstance(k, str) and num_key_re.match(k)]
        if not numeric_keys:
            continue

        for key in sorted(numeric_keys, key=lambda x: int(num_key_re.match(x).group(1))):  # type: ignore[union-attr]
            m = num_key_re.match(key)
            assert m
            stem = Path(key).stem if "." in key else key
            raw = stem_index(stem)
            if raw is None:
                errors.append(f"{deck_id} ключ {key}: не удалось разобрать индекс из ключа")
                continue
            if raw <= 21:
                continue
            desc = section.get(key)
            if not isinstance(desc, str):
                continue
            # По номеру в имени файла, не по INDEX_FIX: описание в JSON отражает картинку этого файла.
            exp = expected_minor(raw)
            if not exp:
                errors.append(f"{deck_id} {key}: индекс {raw}, нет ожидания младшего аркана")
                continue
            exp_rank, exp_suit = exp
            parsed = last_card_label(desc)
            if not parsed:
                continue
            pr, ps = parsed
            if pr != exp_rank or ps != exp_suit:
                msg = (
                    f"{deck_id} {key} (индекс по файлу {raw}): в тексте ранг {pr}, масть {ps}, "
                    f"ожидалось ранг {exp_rank}, масть {exp_suit}"
                )
                if allow_known and (deck_id, key) in KNOWN_LABEL_VS_NUMBER:
                    warnings.append(f"(известное) {msg}")
                else:
                    errors.append(msg)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка колод с числовыми id 0–77")
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Путь к tarot_card_descriptions.json для сверки подписей",
    )
    parser.add_argument("--deck", type=str, default=None, help="Только этот deck_id")
    parser.add_argument(
        "--allow-known-mismatches",
        action="store_true",
        help="Считать предупреждением известные расхождения гравюра/номер (см. KNOWN_LABEL_VS_NUMBER)",
    )
    args = parser.parse_args()

    if not TARO_ROOT.is_dir():
        print(f"Нет папки {TARO_ROOT}", file=sys.stderr)
        return 2

    file_errors: list[str] = []
    print("=== Файлы на диске (числовые 0–77) ===")

    for folder in sorted(TARO_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        deck_id = FOLDER_TO_DECK_ID.get(folder.name.lower())
        if not deck_id:
            continue
        if args.deck and deck_id != args.deck:
            continue

        files, by_idx = collect_numeric_deck_files(folder)
        if not by_idx:
            print(f"{deck_id}: нет файлов с префиксом NN-")
            continue

        fe = verify_file_indices(deck_id, by_idx)
        fe_dup = verify_no_duplicate_prefixes(folder, deck_id)
        fe.extend(fe_dup)

        status = "OK" if not fe else "ОШИБКИ"
        print(f"{deck_id} ({folder.name}): карт {len(by_idx)} {status}")
        if fe:
            file_errors.extend([f"{deck_id}: {line}" for line in fe])
            for line in fe:
                print(line)

    json_errors: list[str] = []
    if args.json:
        path = args.json if args.json.is_absolute() else ROOT / args.json
        if not path.is_file():
            print(f"Нет JSON: {path}", file=sys.stderr)
            return 2
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print("JSON: ожидался объект на верхнем уровне", file=sys.stderr)
            return 2
        print("\n=== Подписи в JSON (ключи NN-..., только младшие арканы 22–77) ===")
        json_errors, json_warnings = verify_json_labels(
            data, args.deck, allow_known=args.allow_known_mismatches
        )
        for line in json_warnings:
            print(f"ПРЕДУПРЕЖДЕНИЕ: {line}")
        if not json_errors:
            print("Несоответствий ранг/масть не найдено.")
        else:
            for line in json_errors:
                print(line)

    total = len(file_errors) + len(json_errors)
    if total:
        print(f"\nИтого проблем: {total}")
        return 1
    print("\nИтог: без проблем.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
