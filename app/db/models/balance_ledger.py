"""BalanceLedger: FIFO pools of balance per tariff version for versioned pricing."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class BalanceLedger(Base):
    """
    Ledger entries for user balance. Each topup creates an entry.
    Deducts consume from oldest entries first (FIFO).
    tariff_version: which tariff applies to this pool (1, 2, ...).
    """

    __tablename__ = "balance_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # remaining, can go to 0
    tariff_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
