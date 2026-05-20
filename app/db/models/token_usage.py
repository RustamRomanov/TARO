"""Token usage model: per-request AI token and cost tracking."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TokenUsage(Base):
    """Record of one AI request: provider, model, tokens, cost (USD/RUB)."""

    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    feature_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_rub: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_token_usage_user_id", "user_id"),
        Index("ix_token_usage_created_at", "created_at"),
        Index("ix_token_usage_feature", "feature_type"),
        Index("ix_token_usage_provider", "provider"),
    )
