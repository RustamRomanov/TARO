"""Каталог пользовательских файлов: аватары, вложения поддержки.

По умолчанию: ``app/static/uploads`` внутри образа (данные пропадают при деплое на Railway).

В продакшене задайте ``ASTROV_UPLOADS_DIR`` (абсолютный путь) и смонтируйте Railway Volume
на тот же путь. См. ``docs/railway-uploads-volume.md``.
"""

from pathlib import Path

from app.core.config import get_settings

# Относительный каталог по умолчанию (локальная разработка, контейнер без тома).
_DEFAULT_UPLOADS = Path(__file__).resolve().parent.parent / "static" / "uploads"


def get_uploads_root() -> Path:
    raw = (get_settings().ASTROV_UPLOADS_DIR or "").strip()
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        root = _DEFAULT_UPLOADS.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploads_public_path_to_fs(web_path: str) -> Path:
    """``/uploads/avatars/…`` или ``/uploads/support/…`` в путь на диске под корнем загрузок."""
    s = (web_path or "").strip()
    prefix = "/uploads/"
    if not s.startswith(prefix):
        raise ValueError(f"Expected path starting with {prefix!r}, got {web_path!r}")
    rel = s[len(prefix) :].lstrip("/")
    return get_uploads_root() / rel
