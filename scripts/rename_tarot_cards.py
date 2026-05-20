#!/usr/bin/env python3
"""
Переименовывает изображения карт Таро в папках frontend/src/assets/taro/*/
в стандартные имена: 00-Major-Fool.jpg ... 21-Major-World.jpg,
22-Wands1.jpg ... 77-Pentacles14.jpg (порядок: 22 старших, затем жезлы, кубки, мечи, пентакли).
Рубашка, Колода и Аннотация не трогаем.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARO = ROOT / "frontend" / "src" / "assets" / "taro"

# 78 карт: 0–21 старшие арканы, затем Wands 1–14, Cups 1–14, Swords 1–14, Pentacles 1–14
MAJOR_NAMES = [
    "Fool", "Magician", "Priestess", "Empress", "Emperor", "Hierophant",
    "Lovers", "Chariot", "Strength", "Hermit", "Wheel", "Justice",
    "Hanged", "Death", "Temperance", "Devil", "Tower", "Star", "Moon", "Sun",
    "Judgement", "World",
]
def build_targets():
    out = [f"{i:02d}-Major-{MAJOR_NAMES[i]}" for i in range(22)]
    for suit, start in [("Wands", 22), ("Cups", 36), ("Swords", 50), ("Pentacles", 64)]:
        for k in range(1, 15):
            out.append(f"{start + k - 1}-{suit}{k}")
    return out

TARGET_BASENAMES = build_targets()
assert len(TARGET_BASENAMES) == 78, len(TARGET_BASENAMES)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP = {"рубашка", "колода", "аннотация", "annotation"}
SKIP_SUBSTR = ["/doc/"]


def is_skip(path: Path, name: str) -> bool:
    name_lower = name.lower()
    for s in SKIP:
        if s in name_lower:
            return True
    for sub in SKIP_SUBSTR:
        if sub in str(path).lower():
            return True
    return False


def main():
    if not TARO.exists():
        print("Папка taro не найдена:", TARO)
        return
    for deck_dir in sorted(TARO.iterdir()):
        if not deck_dir.is_dir():
            continue
        images = []
        for f in deck_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in IMAGE_EXTS:
                continue
            if is_skip(f, f.name):
                continue
            # только файлы непосредственно в папке колоды (без doc/ и т.д.)
            if f.parent != deck_dir:
                continue
            images.append(f)
        images.sort(key=lambda p: p.name)
        if len(images) < 78:
            print(f"{deck_dir.name}: найдено {len(images)} карт (ожидается 78), пропуск")
            continue
        # уже переименованы (есть файл вида 00-Major-Fool.jpg)
        if re.match(r"^\d{2}-Major-", images[0].stem, re.I) or re.match(r"^\d+-Wands\d+", images[0].stem, re.I):
            print(f"{deck_dir.name}: уже в целевом формате, пропуск")
            continue
        images = images[:78]
        # переименование через временные имена
        temp_renames = []
        for i, f in enumerate(images):
            temp = deck_dir / f"__tmp_{i}{f.suffix}"
            temp_renames.append((f, temp))
        for old, temp in temp_renames:
            old.rename(temp)
        for i, (_, temp) in enumerate(temp_renames):
            final_name = TARGET_BASENAMES[i] + ".jpg"
            final = deck_dir / final_name
            temp.rename(final)
        print(f"Переименовано 78 карт в {deck_dir.name}")


if __name__ == "__main__":
    main()
