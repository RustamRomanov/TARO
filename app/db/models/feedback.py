"""Feedback model: user messages (complaints/suggestions) for support."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class Feedback(Base):
    """User feedback: message, status (new/read/resolved)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="feedback")
    attachments: Mapped[list["FeedbackAttachment"]] = relationship(
        "FeedbackAttachment",
        back_populates="feedback",
        cascade="all, delete-orphan",
    )
    replies: Mapped[list["FeedbackReply"]] = relationship(
        "FeedbackReply",
        back_populates="feedback",
        cascade="all, delete-orphan",
    )
