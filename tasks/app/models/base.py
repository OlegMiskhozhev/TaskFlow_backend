from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from database.db import Base


class BaseCreated(Base):
    """Абстрактная модель с полем даты создания объекта."""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BaseName(Base):
    """Абстрактная модель с полем имени объекта."""

    __abstract__ = True

    name: Mapped[str] = mapped_column(String(150), nullable=False)
