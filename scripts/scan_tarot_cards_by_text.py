#!/usr/bin/env python3
"""
Переименовывает карты Таро по ТЕКСТУ, написанному на самой карте (как на изображении).
Спрашивает у Vision только: «Какой текст на карте?» и делает из него имя файла.
Подходит для любых колод (в т.ч. Nightmare Before Christmas с «KING OF PRESENTS» и т.д.).

Запуск:
  cd ASTROV && . venv/bin/activate && python3 scripts/scan_tarot_cards_by_text.py

Требуется: OPENAI_API_KEY или AI_API_KEY + AI_VISION_MODEL в .env
"""
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARO_ROOT = ROOT / "frontend" / "src" / "assets" / "taro"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP = {"рубашка", "колода", "аннотация", "annotation"}


def sanitize_basename(text: str, max_len: int = 60) -> str:
    """Текст с карты -> безопасное имя файла (латиница, цифры, дефис)."""
    if not text or not isinstance(text, str):
        return "Unknown"
    # убрать лишнее, оставить буквы/цифры/пробелы
    t = re.sub(r"[^\w\s\-]", "", text, flags=re.U)
    t = re.sub(r"\s+", "-", t.strip())
    t = re.sub(r"-+", "-", t).strip("-")
    if not t:
        return "Unknown"
    # Title case для читаемости
    t = t.title()
    return t[:max_len] if len(t) > max_len else t


async def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    from app.services.ai_client import AIServiceClient

    if not TARO_ROOT.exists():
        print(f"Папка не найдена: {TARO_ROOT}")
        sys.exit(1)

    client = AIServiceClient()
    prompt = (
        "What is the EXACT text written on this tarot card (the card title or label)? "
        "Reply with ONLY that text, in English, as it appears on the card. "
        "One line, use spaces between words. Examples: KING OF PRESENTS, THE FOOL, THREE OF WANDS, PAGE OF CUPS."
    )
    system = "You read and return only the card title text. No explanation, no JSON, no quotes."

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
        if not images:
            continue
        n = len(images)
        print(f"\n{deck_dir.name}: {n} карт")

        identified: list[tuple[Path, str]] = []
        for i, img_path in enumerate(images):
            print(f"  [{i + 1}/{n}] {img_path.name}...", end=" ", flush=True)
            try:
                image_bytes = img_path.read_bytes()
                out = await client.analyze_image(image_bytes, prompt, system_prompt=system)
                raw = out.get("raw") or str(out)
                if isinstance(raw, dict):
                    raw = raw.get("description", raw.get("text", str(raw)))
                text = (raw or "").strip().strip('"\'')
                base = sanitize_basename(text)
                identified.append((img_path, base))
                print(base)
            except Exception as e:
                print(f"err: {e}")

        if not identified:
            continue

        # Временно в __tmp_0, __tmp_1, ...
        temp_list = []
        for img_path, base in identified:
            t = deck_dir / f"__tmp_{len(temp_list)}{img_path.suffix}"
            temp_list.append((img_path, t, base))
        for old, t, _ in temp_list:
            old.rename(t)

        # Финальные имена: 01-King-Of-Presents.jpg, 02-..., чтобы порядок сохранялся
        seen: dict[str, int] = {}
        for idx, (_, temp_path, base) in enumerate(temp_list):
            final_base = f"{idx + 1:02d}-{base}"
            if seen.get(base, 0) > 0:
                final_base = f"{idx + 1:02d}-{base}-{seen[base] + 1}"
            seen[base] = seen.get(base, 0) + 1
            final = deck_dir / f"{final_base}.jpg"
            temp_path.rename(final)
        print(f"  Готово: переименовано {len(identified)} файлов.")


if __name__ == "__main__":
    asyncio.run(main())
