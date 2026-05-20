"""Revenue: поступления по дням (для агрегации за день/неделю/месяц)."""
from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class Revenue(Base):
    """Поступления за дату (рубли или условные единицы). payment_id для дедупликации при backfill."""

    __tablename__ = "revenue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_date: Mapped[date] = mapped_column(Date(), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
