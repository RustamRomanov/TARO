"""User model: Telegram user + subscription status + daily limits."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    User table: Telegram user, subscription status, daily limit counters.
    Counters reset at 00:00 UTC when last_reset_date < today.
    """

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_next_charge_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_payment_method_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    referred_by_telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    daily_tarot: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_vision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_dreams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reset_date: Mapped[Optional[date]] = mapped_column(
        Date(),
        server_default=func.current_date(),
        onupdate=func.current_date(),
        nullable=True,
    )

    #: Последний известный статус пользователя в личном чате с ботом (member, kicked, left, …), см. Telegram ChatMemberUpdated
    bot_member_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    #: Когда зафиксировали остановку/блокировку бота (my_chat_member или ошибка доставки). None, если снова открыли бота
    bot_stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["History"]] = relationship(
        "History",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        "Feedback",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    payment_methods: Mapped[list["UserPaymentMethod"]] = relationship(
        "UserPaymentMethod",
        back_populates="user",
        cascade="all, delete-orphan",
    )
