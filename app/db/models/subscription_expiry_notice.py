"""Фиксация отправленных напоминаний об окончании Тарифа VIP (7 / 3 / 2 / 1 день)."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SubscriptionExpiryNotice(Base):
    """Одна запись: пользователь, дата окончания периода, за сколько дней отправили."""

    __tablename__ = "subscription_expiry_notices"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "period_end",
            "bucket",
            name="uq_subscription_expiry_user_period_bucket",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    bucket: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
