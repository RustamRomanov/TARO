"""Profile model: person (owner or partner) linked to a Telegram user."""
from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, Float, ForeignKey, Integer, JSON, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class Profile(Base):
    """
    Profile (person): name, birth data. Belongs to a user.
    is_primary=True for the account owner (one per user).
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # m / f / other
    gender_source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # manual / auto
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    birth_time: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    birth_city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    birth_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    birth_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    relationship_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    interests: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="profiles")
