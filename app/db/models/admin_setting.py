"""Admin settings: key-value store (e.g. USD_RUB exchange rate)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class AdminSetting(Base):
    """Key-value settings for admin (exchange rate, etc.)."""

    __tablename__ = "admin_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


ADMIN_SETTING_USD_RUB = "usd_rub_rate"
