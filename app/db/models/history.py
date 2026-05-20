"""History model: log of AI requests (tarot, vision, dream, numerology)."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class HistoryType(str, enum.Enum):
    """Type of AI request."""

    TAROT = "tarot"
    VISION = "vision"
    DREAM = "dream"
    NUMEROLOGY = "numerology"
    NATAL = "natal"
    KEYS = "keys"
    SHADOW = "shadow"
    FORECAST = "forecast"


class History(Base):
    """History of user requests: type, request content, AI response, tokens and cost."""

    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[HistoryType] = mapped_column(
        Enum(HistoryType, native_enum=False),
        nullable=False,
    )
    request_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="history")
