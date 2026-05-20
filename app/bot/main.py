"""Bot and Dispatcher setup, polling entry point."""
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot.handlers import router as handlers_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_token: Optional[str] = _settings.TELEGRAM_BOT_TOKEN or None

if _token and _token.strip():
    bot = Bot(
        token=_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
else:
    bot = None
    print("Bot token is empty, running without Telegram bot")

dp = Dispatcher()
dp.include_router(handlers_router)


async def setup_bot_commands() -> None:
    """Команды в меню Telegram (список при вводе / у поля сообщения)."""
    if bot is None:
        return
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Приложение ASTROV"),
                BotCommand(command="support", description="Написать в поддержку"),
                BotCommand(command="cancel", description="Отменить обращение"),
            ],
        )
    except Exception:
        logger.exception("set_my_commands failed")


async def run_polling() -> None:
    """Run bot in long-polling mode. Uses token from config (TELEGRAM_BOT_TOKEN)."""
    token = get_settings().TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; bot polling will not start.")
        return
    try:
        await setup_bot_commands()
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def get_bot() -> Bot:
    """Return configured Bot instance (token from config)."""
    return bot


def get_dispatcher() -> Dispatcher:
    """Return configured Dispatcher instance."""
    return dp
