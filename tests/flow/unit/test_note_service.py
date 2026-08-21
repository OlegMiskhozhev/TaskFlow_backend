"""Unit-тесты сервисного слоя заметок flow на тестовой БД."""

from datetime import date

import pytest
from flow.app.schemas.flow import NoteCreate, NoteStatusUpdate, NoteUpdate
from flow.app.services.flow import (
    add_object,
    create_note,
    delete_note,
    get_calendar_note_dates,
    get_note,
    get_notes,
    get_object,
    update_note,
    update_note_status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.flow import Note


@pytest.mark.asyncio
async def test_create_note_sets_owner_and_persists_data(
    own_user_id: int,
) -> None:
    """Проверяет создание заметки и привязку к текущему пользователю."""
    note = await create_note(
        note_data=NoteCreate(
            content='Первая заметка', note_date=date(2026, 5, 1)
        ),
        user_id=own_user_id,
    )

    assert note.id is not None
    assert note.user_id == own_user_id
    assert note.content == 'Первая заметка'
    assert note.note_date == date(2026, 5, 1)
    assert note.is_completed is False


@pytest.mark.asyncio
async def test_get_notes_applies_user_filter_date_pagination_and_order(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет фильтрацию, сортировку и пагинацию get_notes."""
    second_by_id = await note_factory(
        user_id=own_user_id,
        content='Вторая по id',
        note_date=date(2026, 5, 2),
    )
    first = await note_factory(
        user_id=own_user_id,
        content='Первая по id',
        note_date=date(2026, 5, 2),
    )
    await note_factory(
        user_id=own_user_id,
        content='Другой день',
        note_date=date(2026, 5, 3),
    )
    await note_factory(
        user_id=foreign_user_id,
        content='Чужая заметка',
        note_date=date(2026, 5, 2),
    )

    filtered = await get_notes(
        user_id=own_user_id, note_date=date(2026, 5, 2), offset=0, limit=50
    )
    all_notes = await get_notes(
        user_id=own_user_id, note_date=None, offset=0, limit=50
    )
    paged = await get_notes(
        user_id=own_user_id, note_date=None, offset=1, limit=1
    )

    assert [note.id for note in filtered] == [second_by_id.id, first.id]
    assert all(note.user_id == 1 for note in filtered)
    assert len(all_notes) == 3
    assert len(paged) == 1
    assert paged[0].id == all_notes[1].id


@pytest.mark.asyncio
async def test_get_calendar_note_dates_filters_by_month_and_year(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет агрегацию календаря и фильтры month/year."""
    await note_factory(
        user_id=own_user_id,
        content='A',
        note_date=date(2026, 5, 10),
    )
    await note_factory(
        user_id=own_user_id,
        content='B',
        note_date=date(2026, 5, 10),
    )
    await note_factory(
        user_id=own_user_id,
        content='C',
        note_date=date(2026, 6, 1),
    )
    await note_factory(
        user_id=foreign_user_id,
        content='Чужая',
        note_date=date(2026, 5, 10),
    )

    may_dates = await get_calendar_note_dates(
        user_id=own_user_id, month=5, year=2026
    )

    assert may_dates == [(date(2026, 5, 10), 2)]


@pytest.mark.asyncio
async def test_get_calendar_note_dates_filters_by_year_only(
    note_factory,
    own_user_id: int,
) -> None:
    """Проверяет ветку фильтрации календаря только по year."""
    await note_factory(
        user_id=own_user_id, content='Y2026', note_date=date(2026, 1, 10)
    )
    await note_factory(
        user_id=own_user_id, content='Y2025', note_date=date(2025, 1, 10)
    )

    dates = await get_calendar_note_dates(user_id=own_user_id, year=2026)

    assert dates == [(date(2026, 1, 10), 1)]


@pytest.mark.asyncio
async def test_get_object_returns_entity_and_none(
    note_factory,
    own_user_id: int,
) -> None:
    """Проверяет get_object для существующей и отсутствующей записи."""
    note = await note_factory(
        user_id=own_user_id,
        content='Object test',
        note_date=date(2026, 5, 9),
    )

    existing = await get_object(model=Note, object_id=note.id)
    missing = await get_object(model=Note, object_id=999999)

    assert existing is not None and existing.id == note.id
    assert missing is None


@pytest.mark.asyncio
async def test_add_object_creates_note(own_user_id: int) -> None:
    """Проверяет успешное создание записи через add_object."""
    created = await add_object(
        model=Note,
        values={
            'content': 'Added via generic helper',
            'note_date': date(2026, 5, 9),
            'user_id': own_user_id,
            'is_completed': False,
        },
    )

    assert isinstance(created, Note)
    assert created.id is not None
    assert created.user_id == own_user_id


@pytest.mark.asyncio
async def test_add_object_raises_sqlalchemy_error_on_commit_failure(
    own_user_id: int,
    force_commit_failure,
) -> None:
    """Проверяет error-ветку add_object при падении commit."""
    force_commit_failure()

    with pytest.raises(SQLAlchemyError):
        await add_object(
            model=Note,
            values={
                'content': 'Commit fail add_object',
                'note_date': date(2026, 5, 10),
                'user_id': own_user_id,
                'is_completed': False,
            },
        )


@pytest.mark.asyncio
async def test_get_note_returns_only_own_note(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет сценарии своя/чужая/нет записи для get_note."""
    own = await note_factory(
        user_id=own_user_id,
        content='Своя',
        note_date=date(2026, 5, 4),
    )
    other = await note_factory(
        user_id=foreign_user_id,
        content='Чужая',
        note_date=date(2026, 5, 4),
    )

    own_result = await get_note(note_id=own.id, user_id=own_user_id)
    foreign_result = await get_note(note_id=other.id, user_id=own_user_id)
    missing_result = await get_note(note_id=999999, user_id=own_user_id)

    assert own_result is not None and own_result.id == own.id
    assert foreign_result is None
    assert missing_result is None


@pytest.mark.asyncio
async def test_create_note_raises_sqlalchemy_error_on_commit_failure(
    own_user_id: int,
    force_commit_failure,
) -> None:
    """Проверяет error-ветку create_note при падении commit."""
    force_commit_failure()

    with pytest.raises(SQLAlchemyError):
        await create_note(
            note_data=NoteCreate(
                content='Fail create', note_date=date(2026, 5, 5)
            ),
            user_id=own_user_id,
        )


@pytest.mark.asyncio
async def test_update_note_handles_empty_patch_foreign_and_missing(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет empty patch и сценарии своя/чужая/нет для update_note."""
    own = await note_factory(
        user_id=own_user_id,
        content='До обновления',
        note_date=date(2026, 5, 5),
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='Чужая',
        note_date=date(2026, 5, 5),
    )

    empty_patch = await update_note(
        note_id=own.id, note_data=NoteUpdate(), user_id=own_user_id
    )
    updated = await update_note(
        note_id=own.id,
        note_data=NoteUpdate(
            content='После обновления', note_date=date(2026, 5, 6)
        ),
        user_id=own_user_id,
    )
    foreign_result = await update_note(
        note_id=foreign.id,
        note_data=NoteUpdate(content='Не должно обновиться'),
        user_id=own_user_id,
    )
    missing_result = await update_note(
        note_id=999999,
        note_data=NoteUpdate(content='Нет записи'),
        user_id=own_user_id,
    )

    assert empty_patch is not None and empty_patch.content == 'До обновления'
    assert updated is not None and updated.content == 'После обновления'
    assert updated is not None and updated.note_date == date(2026, 5, 6)
    assert foreign_result is None
    assert missing_result is None


@pytest.mark.asyncio
async def test_update_note_raises_sqlalchemy_error_on_commit_failure(
    note_factory,
    own_user_id: int,
    force_commit_failure,
) -> None:
    """Проверяет error-ветку update_note при падении commit."""
    note = await note_factory(
        user_id=own_user_id,
        content='Before fail update',
        note_date=date(2026, 5, 11),
    )
    force_commit_failure()

    with pytest.raises(SQLAlchemyError):
        await update_note(
            note_id=note.id,
            note_data=NoteUpdate(content='After fail'),
            user_id=own_user_id,
        )


@pytest.mark.asyncio
async def test_update_note_status_handles_own_foreign_and_missing(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """
    Проверяет смену статуса и сценарии свой/чужой/нет для update_note_status.
    """
    own = await note_factory(
        user_id=own_user_id,
        content='Статус',
        note_date=date(2026, 5, 7),
        is_completed=False,
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='Чужой статус',
        note_date=date(2026, 5, 7),
        is_completed=False,
    )

    updated = await update_note_status(
        note_id=own.id,
        status_data=NoteStatusUpdate(is_completed=True),
        user_id=own_user_id,
    )
    foreign_result = await update_note_status(
        note_id=foreign.id,
        status_data=NoteStatusUpdate(is_completed=True),
        user_id=own_user_id,
    )
    missing_result = await update_note_status(
        note_id=999999,
        status_data=NoteStatusUpdate(is_completed=True),
        user_id=own_user_id,
    )

    assert updated is not None and updated.is_completed is True
    assert foreign_result is None
    assert missing_result is None


@pytest.mark.asyncio
async def test_update_note_status_raises_sqlalchemy_error_on_commit_failure(
    note_factory,
    own_user_id: int,
    force_commit_failure,
) -> None:
    """Проверяет error-ветку update_note_status при падении commit."""
    note = await note_factory(
        user_id=own_user_id,
        content='Before status fail',
        note_date=date(2026, 5, 12),
        is_completed=False,
    )
    force_commit_failure()

    with pytest.raises(SQLAlchemyError):
        await update_note_status(
            note_id=note.id,
            status_data=NoteStatusUpdate(is_completed=True),
            user_id=own_user_id,
        )


@pytest.mark.asyncio
async def test_delete_note_handles_own_foreign_and_missing(
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
    test_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Проверяет удаление заметки в сценариях своя/чужая/нет записи."""
    own = await note_factory(
        user_id=own_user_id,
        content='Удалить меня',
        note_date=date(2026, 5, 8),
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='Чужая для удаления',
        note_date=date(2026, 5, 8),
    )

    deleted = await delete_note(note_id=own.id, user_id=own_user_id)
    foreign_deleted = await delete_note(
        note_id=foreign.id, user_id=own_user_id
    )
    missing_deleted = await delete_note(note_id=999999, user_id=own_user_id)
    async with test_session_maker() as verify_session:
        deleted_note = await verify_session.scalar(
            select(Note).where(Note.id == own.id)
        )

    assert deleted is True
    assert deleted_note is None
    assert foreign_deleted is False
    assert missing_deleted is False


@pytest.mark.asyncio
async def test_delete_note_raises_sqlalchemy_error_on_commit_failure(
    note_factory,
    own_user_id: int,
    force_commit_failure,
) -> None:
    """Проверяет error-ветку delete_note при падении commit."""
    note = await note_factory(
        user_id=own_user_id,
        content='Before delete fail',
        note_date=date(2026, 5, 13),
    )
    force_commit_failure()

    with pytest.raises(SQLAlchemyError):
        await delete_note(note_id=note.id, user_id=own_user_id)
