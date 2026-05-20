"""Payment model: YooKassa payments (subscription, top-up) and balance deductions."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class Payment(Base):
    """
    Payments and balance operations.
    kind: subscription | topup | deduct_tarot | deduct_vision | deduct_dream
    status: pending | succeeded | failed | canceled (for YooKassa); succeeded for deduct.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referral_source_payment_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    yookassa_payment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
