"""Async SQLAlchemy session and engine (SQLAlchemy 2.0 style)."""
import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models.base import Base

_settings = get_settings()
_db_url = _settings.DATABASE_PRIVATE_URL or _settings.DATABASE_URL or "sqlite+aiosqlite:///./local.db"
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

_engine = create_async_engine(
    _db_url,
    echo=_settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"timeout": 10, "command_timeout": 30} if _db_url.startswith("postgresql+asyncpg://") else {},
)
engine = _engine  # exposed for SQLAdmin

_async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
async_session_factory = _async_session_factory
logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: yield async DB session."""
    async with _async_session_factory() as session:
        try:
            yield session
            # Always commit on successful request.
            # Relying on session.new/dirty/deleted after explicit flush() is unsafe:
            # flush can clear those flags while transaction still has DB changes.
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(max_attempts: int = 6, initial_delay_s: float = 2.0) -> None:
    """
    Create tables with startup retries.

    Railway/Postgres can be cold on container start, so the first connection
    attempt may time out. We retry with exponential backoff to avoid false
    startup failures.
    """
    attempt = 0
    delay = max(0.5, float(initial_delay_s))
    last_exc: Exception | None = None

    while attempt < max_attempts:
        attempt += 1
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            if attempt > 1:
                logger.info("DB init succeeded on retry %s/%s", attempt, max_attempts)
            return
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            logger.warning(
                "DB init attempt %s/%s failed, retry in %.1fs: %s",
                attempt,
                max_attempts,
                delay,
                exc.__class__.__name__,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 1.8, 15.0)

    # preserve previous behavior for caller (main.py logs and continues startup)
    assert last_exc is not None
    raise last_exc
