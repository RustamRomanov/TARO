#!/usr/bin/env python3
"""
Скрипт для визуального анализа карт Таро.
Сканирует изображения карт ВСЕХ колод, отправляет в Vision API, сохраняет описания в JSON.

Запуск:
  cd ASTROV
  source venv/bin/activate
  python scripts/analyze_tarot_cards.py
  python scripts/analyze_tarot_cards.py --force
  python scripts/analyze_tarot_cards.py --force --limit 5

Требуется: AI_API_KEY, AI_BASE_URL, AI_VISION_MODEL в .env
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# Добавляем корень проекта в path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TARO_ROOT = ROOT / "frontend" / "src" / "assets" / "taro"
OUTPUT_JSON = ROOT / "app" / "data" / "tarot_card_descriptions.json"

# Папка колоды -> deck_id (совпадает с id в frontend/src/data/tarotDecks.js)
FOLDER_TO_DECK_ID = {
    "oriens animal tarot": "oriens_animal",
    "the nightmare before christmas tarot": "nightmare_christmas",
    "trionfi della luna": "trionfi_luna",
    "the dark mansion tarot": "dark_mansion",
    "rider-waite tarot": "rider_waite",
}

PROMPT = (
    "Опиши ТОЛЬКО то, что реально видно на изображении карты. Без толкования Таро, без значений арканов, "
    "без догадок о сюжете. Структурируй ответ в одном поле description такими блоками (если что-то не видно, "
    "напиши «не различить»):\n"
    "Передний план: кто или что, позы, крупные объекты.\n"
    "Задний план: фон, небо, архитектура, ландшафт.\n"
    "Фигуры: люди, животные, силуэты (если есть).\n"
    "Цвета: основные и акцентные.\n"
    "Символы и детали: предметы, знаки, надписи на карте, рамка, орнамент.\n"
    "Кратко, 4–8 предложений. Только факты с картинки. На русском."
)

SYSTEM_PROMPT = (
    "Ты фиксируешь только визуальные факты с изображения: что нарисовано, какие цвета, кто или что в кадре, "
    "передний и задний план. Не интерпретируй карту Таро и не объясняй смысл. Не выдумывай то, чего не видно. "
    "Русский язык."
)


def get_card_id(filename: str) -> str | None:
    """ID карты: имя файла без расширения. Включаем и лицевые карты, и рубашку/картинку колоды."""
    base = Path(filename).stem
    if not base:
        return None
    return base


def get_deck_id(folder_name: str) -> str | None:
    """Получить deck_id по имени папки (нормализуем к ключу в FOLDER_TO_DECK_ID)."""
    lower = folder_name.lower().strip()
    return FOLDER_TO_DECK_ID.get(lower)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Vision-описания карт Таро для app/data/tarot_card_descriptions.json")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать уже существующие описания (полное обновление)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Обработать только первые N карт (для проверки API)",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from app.services.ai_client import AIServiceClient

    if not TARO_ROOT.exists():
        print(f"Папка колод не найдена: {TARO_ROOT}")
        sys.exit(1)

    client = AIServiceClient()
    results: dict[str, dict[str, str]] = {}
    if OUTPUT_JSON.exists():
        try:
            data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                results = {k: {kk: vv for kk, vv in v.items() if isinstance(vv, str)} for k, v in data.items() if isinstance(v, dict)}
        except Exception:
            pass

    # Собираем все карты всех колод
    tasks: list[tuple[str, Path]] = []
    for folder in sorted(TARO_ROOT.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        deck_id = get_deck_id(folder.name)
        if not deck_id:
            print(f"Пропуск колоды (нет маппинга): {folder.name}")
            continue
        if deck_id not in results:
            results[deck_id] = {}
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
            for img_path in sorted(folder.glob(ext)):
                card_id = get_card_id(img_path.name)
                if card_id:
                    tasks.append((deck_id, img_path))

    if args.limit is not None and args.limit > 0:
        tasks = tasks[: args.limit]

    total = len(tasks)
    print(f"Найдено к обработке: {total} карт (force={'да' if args.force else 'нет'})\n")

    for i, (deck_id, img_path) in enumerate(tasks):
        card_id = get_card_id(img_path.name)
        if not card_id:
            continue
        if not args.force and (results.get(deck_id) or {}).get(card_id, "").strip():
            print(f"[{i + 1}/{total}] {deck_id}/{card_id}... skip (уже есть)")
            continue
        print(f"[{i + 1}/{total}] {deck_id}/{card_id}...", end=" ", flush=True)

        try:
            image_bytes = img_path.read_bytes()
            out = await client.analyze_image(
                image_bytes,
                PROMPT + ' Ответь СТРОГО в формате JSON: {"description": "твоё описание"}.',
                system_prompt=SYSTEM_PROMPT,
            )
            desc = out.get("description") or out.get("raw") or str(out)
            if isinstance(desc, dict):
                desc = desc.get("text", desc.get("description", str(desc)))
            results[deck_id][card_id] = (desc.strip() if isinstance(desc, str) else str(desc))[:2500]
            print("OK")
        except Exception as e:
            print(f"Ошибка: {e}")
            # Не затираем старое описание пустой строкой при сбое API

        # Промежуточное сохранение после каждой карты (чтобы не терять прогресс при обрыве)
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    total_desc = sum(len(v) for v in results.values())
    print(f"\nСохранено {total_desc} описаний в {len(results)} колодах: {OUTPUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
