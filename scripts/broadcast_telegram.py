#!/usr/bin/env python3
"""
Разовая рассылка в личку Telegram всем пользователям из таблицы users.

Запуск из корня репозитория (нужны .env с DATABASE_* и TELEGRAM_BOT_TOKEN):

  python3 -m scripts.broadcast_telegram              # только сколько получателей
  python3 -m scripts.broadcast_telegram --send       # реальная отправка

Пауза между сообщениями ~35 мс, чтобы не упереться в лимиты. Ошибки «бот заблокирован»
и прочие пропускаются, в конце печатается сводка.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.db.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("broadcast")

# Текст рассылки (plain text: отдельный Bot без HTML parse_mode).
BROADCAST_TEXT = """⚠️  ВНИМАНИЕ! ⚠️

У нас вышло крутое ОБНОВЛЕНИЕ приложения!
🚀🚀🚀 Теперь всё работает быстрее и удобнее.

Что нового:
• Улучшенный интерфейс ⚡
• Исправлены ошибки ⚡
• Новые функции ⚡

👉 Открывай приложение и проверяй!

п.с. Спасибо, что с нами! 💙"""


async def _load_recipient_ids() -> list[int]:
    async with async_session_factory() as session:
        r = await session.execute(select(User.telegram_id).order_by(User.telegram_id.asc()))
        return [int(x) for x in r.scalars().all()]


async def run(*, do_send: bool) -> int:
    token = (get_settings().TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        logger.error("Бот не настроен: проверьте TELEGRAM_BOT_TOKEN в .env")
        return 2

    ids = await _load_recipient_ids()
    logger.info("Получателей в БД: %s", len(ids))
    if not ids:
        return 0

    if not do_send:
        logger.info("Пробный режим. Для отправки добавьте флаг --send")
        preview = BROADCAST_TEXT[:200].replace("\n", " ")
        logger.info("Превью текста: %s…", preview)
        return 0

    # Отдельный Bot без parse_mode: в HTML-режиме Telegram не даёт <br> в обычных сообщениях.
    bot = Bot(token=token, default=DefaultBotProperties())
    ok = 0
    blocked = 0
    failed = 0
    delay_s = 0.035

    try:
        for chat_id in ids:
            try:
                await bot.send_message(
                    chat_id,
                    BROADCAST_TEXT,
                    disable_web_page_preview=True,
                )
                ok += 1
            except TelegramForbiddenError:
                blocked += 1
            except TelegramRetryAfter as e:
                wait = float(getattr(e, "retry_after", 5) or 5)
                logger.warning("FloodWait %s c для chat_id=%s", wait, chat_id)
                await asyncio.sleep(wait)
                try:
                    await bot.send_message(
                        chat_id,
                        BROADCAST_TEXT,
                        disable_web_page_preview=True,
                    )
                    ok += 1
                except Exception:
                    logger.exception("Повторная отправка не удалась chat_id=%s", chat_id)
                    failed += 1
            except TelegramBadRequest as e:
                logger.warning("BadRequest chat_id=%s: %s", chat_id, e)
                failed += 1
            except Exception:
                logger.exception("Ошибка отправки chat_id=%s", chat_id)
                failed += 1
            await asyncio.sleep(delay_s)
    finally:
        await bot.session.close()

    logger.info("Готово: успешно=%s заблокировали_бота=%s прочие_ошибки=%s", ok, blocked, failed)
    return 0 if failed == 0 else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Рассылка в Telegram всем пользователям из БД")
    p.add_argument(
        "--send",
        action="store_true",
        help="Реально отправить сообщения (без флага только показать число получателей)",
    )
    args = p.parse_args()
    code = asyncio.run(run(do_send=bool(args.send)))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
