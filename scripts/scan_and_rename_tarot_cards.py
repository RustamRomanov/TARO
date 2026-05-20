#!/usr/bin/env python3
"""
Сканирует каждое изображение карты Таро через Vision API, определяет карту и переименовывает файл
в стандартное имя (00-Major-Fool.jpg … 77-Pentacles14.jpg).

Запуск:
  cd ASTROV && source venv/bin/activate
  python scripts/scan_and_rename_tarot_cards.py

Требуется: OPENAI_API_KEY или AI_API_KEY + AI_VISION_MODEL в .env
"""
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARO_ROOT = ROOT / "frontend" / "src" / "assets" / "taro"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP = {"рубашка", "колода", "аннотация", "annotation"}
MAJOR_NAMES = [
    "Fool", "Magician", "Priestess", "Empress", "Emperor", "Hierophant",
    "Lovers", "Chariot", "Strength", "Hermit", "Wheel", "Justice",
    "Hanged", "Death", "Temperance", "Devil", "Tower", "Star", "Moon", "Sun",
    "Judgement", "World",
]


def card_id_to_basename(suit: str, number: int) -> str:
    """(suit, number) -> basename без расширения."""
    suit = (suit or "").strip().lower()
    if suit == "major":
        if 0 <= number <= 21:
            return f"{number:02d}-Major-{MAJOR_NAMES[number]}"
    for s, start in [("wands", 22), ("cups", 36), ("swords", 50), ("pentacles", 64)]:
        if s in suit:
            if 1 <= number <= 14:
                return f"{start + number - 1}-{s.capitalize()}{number}"
    return ""


def parse_vision_response(text: str) -> tuple[str, int] | None:
    """Парсит ответ модели: suit и number. Возвращает (suit, number) или None."""
    text = (text or "").strip().lower()
    # JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            s = (data.get("suit") or data.get("arcana") or "").strip().lower()
            n = data.get("number")
            if n is not None:
                n = int(n)
            if s and n is not None:
                if s == "major" and 0 <= n <= 21:
                    return ("major", n)
                if s in ("wands", "cups", "swords", "pentacles") and 1 <= n <= 14:
                    return (s, n)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Текстовые варианты: "Major 5", "Wands 3", "Three of Wands"
    m = re.search(r"major\s*(\d+)", text)
    if m:
        num = int(m.group(1))
        if 0 <= num <= 21:
            return ("major", num)
    for suit in ("wands", "cups", "swords", "pentacles"):
        m = re.search(rf"{suit}\s*(\d+)", text)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 14:
                return (suit, num)
    # "X of Y"
    rank_names = {
        "ace": 1, "one": 1, "1": 1, "two": 2, "2": 2, "three": 3, "3": 3,
        "four": 4, "4": 4, "five": 5, "5": 5, "six": 6, "6": 6, "seven": 7, "7": 7,
        "eight": 8, "8": 8, "nine": 9, "9": 9, "ten": 10, "10": 10,
        "page": 11, "knight": 12, "queen": 13, "king": 14,
    }
    for suit in ("wands", "cups", "swords", "pentacles"):
        if suit in text:
            for name, num in rank_names.items():
                if re.search(rf"\b{name}\b", text):
                    if 1 <= num <= 14:
                        return (suit, num)
    return None


async def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from app.services.ai_client import AIServiceClient

    if not TARO_ROOT.exists():
        print(f"Папка не найдена: {TARO_ROOT}")
        sys.exit(1)

    client = AIServiceClient()
    prompt = (
        "This image shows one tarot card. Reply with ONLY a JSON object, nothing else: "
        '{"suit": "major" | "wands" | "cups" | "swords" | "pentacles", "number": N}. '
        "For Major Arcana: suit=major, number=0 (Fool) to 21 (World). "
        "For Minor: number=1 (Ace) to 10, 11=Page, 12=Knight, 13=Queen, 14=King. "
        "Example: {\"suit\": \"wands\", \"number\": 3} for Three of Wands."
    )
    system = "You identify tarot cards. Reply only with valid JSON: {\"suit\": \"...\", \"number\": N}."

    for deck_dir in sorted(TARO_ROOT.iterdir()):
        if not deck_dir.is_dir() or deck_dir.name.startswith("."):
            continue
        images = []
        for f in deck_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS:
                continue
            if any(s in f.name.lower() for s in SKIP):
                continue
            images.append(f)
        images.sort(key=lambda p: p.name)
        if len(images) != 78:
            print(f"{deck_dir.name}: карт {len(images)} (нужно 78), пропуск")
            continue

        # Сканируем по текущим файлам, собираем (path, target_basename)
        identified: list[tuple[Path, str]] = []
        for i, img_path in enumerate(images):
            print(f"[{deck_dir.name}] {i + 1}/78 {img_path.name}...", end=" ", flush=True)
            try:
                image_bytes = img_path.read_bytes()
                out = await client.analyze_image(image_bytes, prompt, system_prompt=system)
                raw = out.get("raw") or json.dumps(out)
                if isinstance(raw, dict):
                    raw = json.dumps(raw)
                parsed = parse_vision_response(raw)
                if parsed:
                    suit, num = parsed
                    base = card_id_to_basename(suit, num)
                    if base:
                        identified.append((img_path, base))
                        print(base)
                    else:
                        print("? (unknown mapping)")
                else:
                    print("? (parse failed)")
            except Exception as e:
                print(f"err: {e}")

        # Временные имена, чтобы не перезаписать при совпадении имён
        temp_renames = []
        for img_path, basename in identified:
            t = deck_dir / f"__tmp_{len(temp_renames)}{img_path.suffix}"
            temp_renames.append((img_path, t, basename))
        for old, t, _ in temp_renames:
            old.rename(t)
        # Финальные имена; при дубликатах второй и т.д. -> basename_dup2.jpg
        seen: dict[str, int] = {}
        for _, temp_path, basename in temp_renames:
            final_name = f"{basename}.jpg"
            if seen.get(basename, 0) > 0:
                final_name = f"{basename}_dup{seen[basename] + 1}.jpg"
            seen[basename] = seen.get(basename, 0) + 1
            final = deck_dir / final_name
            temp_path.rename(final)
        print(f"Готово: {deck_dir.name}, определено {len(identified)}/78")


if __name__ == "__main__":
    asyncio.run(main())
