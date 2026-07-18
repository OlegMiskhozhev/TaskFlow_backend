from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from database.db import Base


class Note(Base):
    """Модель заметки пользователя во flow-режиме."""

    __table_args__ = (
        Index('ix_notes_user_id_note_date', 'user_id', 'note_date'),
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_completed: Mapped[bool] = mapped_column(
        default=False, server_default=false(), nullable=False
    )
    user_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
