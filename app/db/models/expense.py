"""Expense: затраты по категориям (комиссии, реклама, налоги, токены) для расчёта прибыли."""
from datetime import date

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base

EXPENSE_CATEGORIES = ("commission", "advertising", "taxes", "tokens")
EXPENSE_CATEGORY_LABELS = {
    "commission": "Комиссии",
    "advertising": "Реклама",
    "taxes": "Налоги",
    "tokens": "Токены",
}


class Expense(Base):
    """Запись о затратах за дату по категории (ЮKassa, реклама, налоги, токены)."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_date: Mapped[date] = mapped_column(Date(), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
