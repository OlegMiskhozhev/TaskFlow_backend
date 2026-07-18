from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

MAX_NOTE_CONTENT_LENGTH = 2000


class NoteBase(BaseModel):
    """Базовые поля заметки, общие для создания и ответа API."""

    content: str = Field(
        min_length=1,
        max_length=MAX_NOTE_CONTENT_LENGTH,
        description='Текст заметки',
    )
    note_date: date = Field(description='Дата заметки')


class NoteCreate(NoteBase):
    """Схема входящих данных для создания заметки текущего пользователя."""


class NoteRead(NoteBase):
    """Схема ответа API с данными сохраненной заметки."""

    id: int = Field(description='Идентификатор заметки')
    is_completed: bool = Field(description='Статус выполнения заметки')
    created_at: datetime = Field(description='Дата создания заметки')
    updated_at: datetime = Field(description='Дата обновления заметки')

    model_config = ConfigDict(from_attributes=True)


class NotesList(BaseModel):
    """Схема представления списка заметок."""

    notes: list[NoteRead] = Field(description='Список заметок')


class NoteUpdate(BaseModel):
    """Схема частичного обновления текста и даты заметки."""

    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_NOTE_CONTENT_LENGTH,
        description='Текст заметки',
    )
    note_date: date | None = Field(
        default=None,
        description='Дата заметки',
    )


class NoteStatusUpdate(BaseModel):
    """Схема изменения статуса выполнения заметки."""

    is_completed: bool = Field(description='Статус выполнения заметки')


class CalendarNoteDate(BaseModel):
    """Схема элемента календаря с количеством заметок за дату."""

    note_date: date = Field(
        alias='date',
        description='Дата, на которую есть заметки',
    )
    notes_count: int = Field(description='Количество заметок за дату')

    model_config = ConfigDict(populate_by_name=True)
