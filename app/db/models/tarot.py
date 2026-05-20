from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.models.base import Base


def _uuid_str() -> str:
    return str(uuid4())


class TarotReading(Base):
    __tablename__ = "tarot_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    spread_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cards: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cards_interpretations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    question_essence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    follow_up_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    advice: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chat_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
