"""Резолюция каталога Jinja2-шаблонов: Docker (/app/templates), локально, ASTROV_TEMPLATES_DIR."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Маркер: админка всегда подключает base.html
_MARKER = Path("admin") / "base.html"


def resolve_templates_directory() -> Path:
    """
    Каталог с шаблонами (подкаталоги admin/, sqladmin/, ...).
    В контейнере ожидается /app/templates рядом с пакетом app/.
    """
    try:
        from app.core.config import get_settings

        raw = (getattr(get_settings(), "ASTROV_TEMPLATES_DIR", None) or "").strip()
        if raw:
            p = Path(raw).expanduser()
            try:
                p = p.resolve()
            except OSError:
                pass
            if p.is_dir() and (p / _MARKER).is_file():
                logger.info("Templates: ASTROV_TEMPLATES_DIR=%s", p)
                return p
            logger.warning(
                "ASTROV_TEMPLATES_DIR=%s: нет каталога или файла %s, пробуем стандартные пути.",
                raw,
                _MARKER,
            )
    except Exception as exc:
        logger.warning("Templates: не удалось прочитать настройки: %s", exc)

    # app/core/templates_path.py -> parents[2] = корень репозитория (родитель пакета app/)
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "templates",
        Path("/app/templates"),
        Path.cwd() / "templates",
    ]
    for c in candidates:
        try:
            cres = c.resolve()
        except OSError:
            cres = c
        if cres.is_dir() and (cres / _MARKER).is_file():
            logger.info("Templates directory: %s", cres)
            return cres

    fallback = repo_root / "templates"
    try:
        fb = fallback.resolve()
    except OSError:
        fb = fallback
    logger.error(
        "Не найден каталог шаблонов (ожидается %s внутри). Пробовали: %s, cwd=%s",
        _MARKER,
        [str(x) for x in candidates],
        Path.cwd(),
    )
    return fb
