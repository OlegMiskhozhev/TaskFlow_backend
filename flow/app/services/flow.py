"""
Сервисный слой для работы с заметками flow-режима.

Модуль инкапсулирует операции с БД для заметок и следит, чтобы чтение,
обновление и удаление выполнялись только в пределах текущего пользователя.
"""

from datetime import date

from sqlalchemy import extract, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import Base, connection
from models.flow import Note
from schemas.flow import NoteCreate, NoteStatusUpdate, NoteUpdate


async def _get_note_by_user(
    note_id: int,
    user_id: int,
    session: AsyncSession,
) -> Note | None:
    """Возвращает заметку пользователя внутри уже открытой сессии."""
    result = await session.execute(
        select(Note).where(
            Note.id == note_id,
            Note.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


@connection
async def get_object(
    model: type[Base],
    object_id: int,
    session: AsyncSession,
) -> Base | None:
    """Возвращает объект модели по идентификатору без проверки владельца."""
    item = await session.get(model, object_id)
    return item if item else None


@connection
async def add_object(
    model: type[Base],
    values: dict,
    session: AsyncSession,
) -> Base:
    """Создает запись модели из переданных значений и сохраняет ее в БД."""
    new_item = model(**values)
    session.add(new_item)
    try:
        await session.commit()
        await session.refresh(new_item)
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    return new_item


@connection
async def create_note(
    note_data: NoteCreate,
    user_id: int,
    session: AsyncSession,
) -> Note:
    """
    Создает заметку и привязывает ее к текущему пользователю.

    Клиентские данные используются только для полей заметки, а владелец
    всегда задается сервером через `user_id`.
    """
    note = Note(
        **note_data.model_dump(),
        user_id=user_id,
    )
    session.add(note)
    try:
        await session.commit()
        await session.refresh(note)
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    return note


@connection
async def get_notes(
    user_id: int,
    session: AsyncSession,
    note_date: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[Note]:
    """
    Возвращает страницу заметок текущего пользователя.

    Опционально фильтрует записи по дате. Результат сортируется по дате
    заметки и идентификатору, чтобы страницы были стабильными.
    """
    query = select(Note).where(Note.user_id == user_id)
    if note_date is not None:
        query = query.where(Note.note_date == note_date)

    result = await session.execute(
        query.order_by(Note.note_date, Note.id).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


@connection
async def get_calendar_note_dates(
    user_id: int,
    session: AsyncSession,
    month: int | None = None,
    year: int | None = None,
) -> list[tuple[date, int]]:
    """
    Возвращает даты с количеством заметок текущего пользователя.

    Фильтры по месяцу и году применяются к `note_date`; результат отсортирован
    по дате для удобного отображения календаря.
    """
    query = (
        select(
            Note.note_date,
            func.count(Note.id).label('notes_count'),
        )
        .where(Note.user_id == user_id)
        .group_by(Note.note_date)
        .order_by(Note.note_date)
    )

    if month is not None:
        query = query.where(extract('month', Note.note_date) == month)
    if year is not None:
        query = query.where(extract('year', Note.note_date) == year)

    result = await session.execute(query)
    return [
        (note_date, notes_count) for note_date, notes_count in result.all()
    ]


@connection
async def get_note(
    note_id: int,
    user_id: int,
    session: AsyncSession,
) -> Note | None:
    """Возвращает заметку только если она принадлежит текущему пользователю."""
    return await _get_note_by_user(
        note_id=note_id,
        user_id=user_id,
        session=session,
    )


@connection
async def update_note(
    note_id: int,
    note_data: NoteUpdate,
    user_id: int,
    session: AsyncSession,
) -> Note | None:
    """
    Обновляет редактируемые поля заметки текущего пользователя.

    Если заметка не найдена или принадлежит другому пользователю, возвращает
    `None`; пустой набор изменений оставляет запись без изменений.
    """
    note = await _get_note_by_user(
        note_id=note_id,
        user_id=user_id,
        session=session,
    )
    if note is None:
        return None

    values = note_data.model_dump(exclude_unset=True)
    if not values:
        return note

    for field, value in values.items():
        setattr(note, field, value)

    try:
        await session.commit()
        await session.refresh(note)
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    return note


@connection
async def update_note_status(
    note_id: int,
    status_data: NoteStatusUpdate,
    user_id: int,
    session: AsyncSession,
) -> Note | None:
    """
    Изменяет только статус выполнения заметки текущего пользователя.

    Остальные поля заметки не затрагиваются, чтобы отделить смену статуса от
    редактирования содержимого.
    """
    note = await _get_note_by_user(
        note_id=note_id,
        user_id=user_id,
        session=session,
    )
    if note is None:
        return None

    note.is_completed = status_data.is_completed
    try:
        await session.commit()
        await session.refresh(note)
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    return note


@connection
async def delete_note(
    note_id: int,
    user_id: int,
    session: AsyncSession,
) -> bool:
    """
    Удаляет заметку текущего пользователя.

    Возвращает `False`, если заметка не найдена или недоступна пользователю,
    чтобы роутер мог преобразовать результат в корректный HTTP-ответ.
    """
    note = await _get_note_by_user(
        note_id=note_id,
        user_id=user_id,
        session=session,
    )
    if note is None:
        return False

    try:
        await session.delete(note)
        await session.commit()
    except SQLAlchemyError as e:
        await session.rollback()
        raise e
    return True
