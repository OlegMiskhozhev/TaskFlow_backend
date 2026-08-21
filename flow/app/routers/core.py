"""
Маршруты API заметок для flow-режима.

Модуль определяет FastAPI-эндпоинты для операций с заметками:
- создание заметок;
- получение списка заметок с фильтрацией по дате;
- получение списка заметок на выбранную дату;
- получение деталей заметки;
- обновление текста, даты и статуса выполнения заметки;
- удаление заметок.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import TypeAdapter

from core.dependency import CurrentUserIdDependency
from core.redis import redis_service
from schemas.flow import (
    CalendarNoteDate,
    NoteCreate,
    NoteRead,
    NotesList,
    NoteStatusUpdate,
    NoteUpdate,
)
from services.flow import (
    create_note,
    delete_note,
    get_calendar_note_dates,
    get_note,
    get_notes,
    update_note,
    update_note_status,
)

core_router = APIRouter(prefix='/notes', tags=['Заметки'])

NOTES_CACHE_TTL_SECONDS = 300
NOTES_CACHE_PREFIX = 'flow:notes'
NOTES_LIST_TYPE_ADAPTER = TypeAdapter(NotesList)
CALENDAR_NOTE_DATES_TYPE_ADAPTER = TypeAdapter(list[CalendarNoteDate])


def _get_notes_list_cache_key(
    *,
    user_id: int,
    note_date: date | None,
    offset: int,
    limit: int,
) -> str:
    """Сформировать ключ кэша списка заметок пользователя."""
    date_part = f'date:{note_date.isoformat()}' if note_date else 'all'
    return (
        f'{NOTES_CACHE_PREFIX}:{user_id}:list:'
        f'{date_part}:{offset}:{limit}'
    )


def _get_calendar_cache_key(
    *,
    user_id: int,
    month: int | None,
    year: int | None,
) -> str:
    """Сформировать ключ кэша календаря заметок пользователя."""
    month_part = month if month is not None else 'all'
    year_part = year if year is not None else 'all'
    return (
        f'{NOTES_CACHE_PREFIX}:{user_id}:calendar:'
        f'{month_part}:{year_part}'
    )


async def _invalidate_notes_cache(user_id: int) -> None:
    """Сбросить все кешированные данные заметок пользователя."""
    await redis_service.invalidate(f'{NOTES_CACHE_PREFIX}:{user_id}:*')

NOTE_EXAMPLE = {
    'id': 1,
    'content': 'Подготовить план задач на день',
    'note_date': '2026-05-04',
    'is_completed': False,
    'created_at': '2026-05-04T10:00:00Z',
    'updated_at': '2026-05-04T10:00:00Z',
}

NOTE_NOT_FOUND_RESPONSE = {
    'description': 'Заметка не найдена или недоступна текущему пользователю',
    'content': {
        'application/json': {
            'example': {'detail': 'Note not found'},
        }
    },
}

VALIDATION_ERROR_RESPONSE = {
    'description': 'Ошибка валидации данных запроса',
}

AUTH_ERROR_RESPONSE = {
    'description': 'Проблема авторизации или недоступна проверка токена',
    'content': {
        'application/json': {
            'example': {'detail': 'Invalid or expired access token'},
        }
    },
}

CALENDAR_NOTE_DATE_EXAMPLE = {
    'date': '2026-05-04',
    'notes_count': 3,
}


@core_router.get(
    '/',
    response_model=NotesList,
    summary='Получить список заметок',
    description="""
    Получение заметок текущего пользователя в объекте с полем `notes`.

    **Фильтрация и пагинация:**
    - `note_date`: опциональный фильтр по дате заметки
    - Формат даты: `YYYY-MM-DD`
    - `offset`: сколько записей пропустить
    - `limit`: сколько записей вернуть, максимум 100

    **Доступ:**
    Эндпоинт возвращает только заметки пользователя из `current_user_id`.

    **Примечание:** Возвращает `{"notes": []}`, если заметок нет.
    """,
    responses={
        200: {
            'description': (
                'Список заметок текущего пользователя в поле `notes`'
            ),
            'content': {
                'application/json': {
                    'example': {
                        'notes': [
                            NOTE_EXAMPLE,
                            {
                                **NOTE_EXAMPLE,
                                'id': 2,
                                'content': 'Проверить прогресс по flow API',
                                'is_completed': True,
                            },
                        ],
                    },
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_notes_list(
    current_user_id: CurrentUserIdDependency,
    note_date: date | None = Query(
        default=None,
        description='Фильтр по дате заметки в формате YYYY-MM-DD',
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description='Количество заметок, которое нужно пропустить',
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description='Максимальное количество заметок в ответе',
    ),
) -> NotesList:
    cache_key = _get_notes_list_cache_key(
        user_id=current_user_id,
        note_date=note_date,
        offset=offset,
        limit=limit,
    )
    cached_notes = await redis_service.get(cache_key)
    if cached_notes is not None:
        return NOTES_LIST_TYPE_ADAPTER.validate_json(cached_notes)

    notes = await get_notes(
        user_id=current_user_id,
        note_date=note_date,
        offset=offset,
        limit=limit,
    )
    notes_list = NotesList(
        notes=[NoteRead.model_validate(note) for note in notes],
    )

    await redis_service.set(
        key=cache_key,
        value=notes_list.model_dump_json(),
        ttl=NOTES_CACHE_TTL_SECONDS,
    )
    return notes_list


@core_router.get(
    '/calendar',
    response_model=list[CalendarNoteDate],
    summary='Получить календарь заметок',
    description="""
    Получение дат, на которые у текущего пользователя есть заметки.

    **Фильтрация:**
    - `month`: опциональный номер месяца от 1 до 12
    - `year`: опциональный год

    **Доступ:**
    Эндпоинт учитывает только заметки пользователя из `current_user_id`.
    """,
    responses={
        200: {
            'description': 'Даты с количеством заметок текущего пользователя',
            'content': {
                'application/json': {
                    'example': [
                        CALENDAR_NOTE_DATE_EXAMPLE,
                        {
                            **CALENDAR_NOTE_DATE_EXAMPLE,
                            'date': '2026-05-05',
                            'notes_count': 1,
                        },
                    ],
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_notes_calendar(
    current_user_id: CurrentUserIdDependency,
    month: int | None = Query(
        default=None,
        ge=1,
        le=12,
        description='Фильтр по номеру месяца',
    ),
    year: int | None = Query(
        default=None,
        ge=1,
        description='Фильтр по году',
    ),
) -> list[CalendarNoteDate]:
    cache_key = _get_calendar_cache_key(
        user_id=current_user_id,
        month=month,
        year=year,
    )
    cached_calendar_dates = await redis_service.get(cache_key)
    if cached_calendar_dates is not None:
        return CALENDAR_NOTE_DATES_TYPE_ADAPTER.validate_json(
            cached_calendar_dates,
        )

    calendar_dates = await get_calendar_note_dates(
        user_id=current_user_id,
        month=month,
        year=year,
    )
    calendar_note_dates = [
        CalendarNoteDate(note_date=note_date, notes_count=notes_count)
        for note_date, notes_count in calendar_dates
    ]

    await redis_service.set(
        key=cache_key,
        value=CALENDAR_NOTE_DATES_TYPE_ADAPTER.dump_json(
            calendar_note_dates,
        ).decode(),
        ttl=NOTES_CACHE_TTL_SECONDS,
    )
    return calendar_note_dates


@core_router.get(
    '/date/{note_date}',
    response_model=NotesList,
    summary='Получить заметки на дату',
    description="""
    Получение заметок текущего пользователя на конкретный день в объекте с
    полем `notes`.

    **Пагинация:**
    - `offset`: сколько записей пропустить
    - `limit`: сколько записей вернуть, максимум 100

    **Доступ:**
    Возвращаются только заметки пользователя из `current_user_id`.

    **Примечание:** Возвращает `{"notes": []}`, если на эту дату заметок нет.
    """,
    responses={
        200: {
            'description': (
                'Объект со списком заметок на указанную дату в поле `notes`'
            ),
            'content': {
                'application/json': {
                    'example': {
                        'notes': [
                            NOTE_EXAMPLE,
                            {
                                **NOTE_EXAMPLE,
                                'id': 2,
                                'content': 'Проверить прогресс по flow API',
                                'is_completed': True,
                            },
                        ],
                    },
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_notes_by_date(
    current_user_id: CurrentUserIdDependency,
    note_date: date = Path(
        description='Дата заметок в формате YYYY-MM-DD',
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description='Количество заметок, которое нужно пропустить',
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description='Максимальное количество заметок в ответе',
    ),
) -> NotesList:
    cache_key = _get_notes_list_cache_key(
        user_id=current_user_id,
        note_date=note_date,
        offset=offset,
        limit=limit,
    )
    cached_notes = await redis_service.get(cache_key)
    if cached_notes is not None:
        return NOTES_LIST_TYPE_ADAPTER.validate_json(cached_notes)

    notes = await get_notes(
        user_id=current_user_id,
        note_date=note_date,
        offset=offset,
        limit=limit,
    )
    notes_list = NotesList(
        notes=[NoteRead.model_validate(note) for note in notes],
    )

    await redis_service.set(
        key=cache_key,
        value=notes_list.model_dump_json(),
        ttl=NOTES_CACHE_TTL_SECONDS,
    )
    return notes_list


@core_router.post(
    '/',
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary='Создать заметку',
    description="""
    Создание новой заметки для текущего пользователя.

    **Правила:**
    - `user_id` не принимается от клиента
    - Владелец заметки определяется через `current_user_id`
    - `content` должен быть непустой строкой
    - `is_completed` при создании устанавливается значением по умолчанию

    **Доступ:**
    Созданная заметка сразу привязана к текущему пользователю.
    """,
    responses={
        201: {
            'description': 'Заметка успешно создана',
            'content': {
                'application/json': {
                    'example': NOTE_EXAMPLE,
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def create_note_item(
    note_data: NoteCreate,
    current_user_id: CurrentUserIdDependency,
) -> NoteRead:
    note = await create_note(
        note_data=note_data,
        user_id=current_user_id,
    )
    await _invalidate_notes_cache(current_user_id)
    return NoteRead.model_validate(note)


@core_router.get(
    '/{note_id}',
    response_model=NoteRead,
    summary='Получить заметку',
    description="""
    Получение одной заметки по ID.

    **Проверки:**
    - Заметка должна существовать
    - Заметка должна принадлежать текущему пользователю
    - `note_id` должен быть положительным числом

    **Доступ:**
    Чужие заметки не раскрываются и возвращают `404`.
    """,
    responses={
        200: {
            'description': 'Данные заметки',
            'content': {
                'application/json': {
                    'example': NOTE_EXAMPLE,
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        404: NOTE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def get_note_item(
    current_user_id: CurrentUserIdDependency,
    note_id: int = Path(description='ID заметки', gt=0),
) -> NoteRead:
    note = await get_note(
        note_id=note_id,
        user_id=current_user_id,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Note not found',
        )

    return NoteRead.model_validate(note)


@core_router.patch(
    '/{note_id}',
    response_model=NoteRead,
    summary='Обновить заметку',
    description="""
    Частичное обновление текста или даты заметки.

    **Что можно изменить:**
    - `content`: текст заметки
    - `note_date`: дата заметки

    **Правила:**
    - `user_id` не принимается от клиента
    - Статус выполнения меняется отдельным эндпоинтом
    - Пустой PATCH без полей вернет текущую заметку без изменений

    **Доступ:**
    Изменить можно только заметку текущего пользователя.
    """,
    responses={
        200: {
            'description': 'Заметка успешно обновлена',
            'content': {
                'application/json': {
                    'example': {
                        **NOTE_EXAMPLE,
                        'content': 'Обновить документацию flow API',
                    },
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        404: NOTE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def update_note_item(
    note_data: NoteUpdate,
    current_user_id: CurrentUserIdDependency,
    note_id: int = Path(description='ID заметки', gt=0),
) -> NoteRead:
    note = await update_note(
        note_id=note_id,
        note_data=note_data,
        user_id=current_user_id,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Note not found',
        )

    await _invalidate_notes_cache(current_user_id)
    return NoteRead.model_validate(note)


@core_router.patch(
    '/{note_id}/status',
    response_model=NoteRead,
    summary='Изменить статус заметки',
    description="""
    Изменение статуса выполнения заметки.

    **Что меняется:**
    - Только поле `is_completed`

    **Сценарии:**
    - `true`: отметить заметку выполненной
    - `false`: вернуть заметку в активное состояние

    **Доступ:**
    Статус можно изменить только у заметки текущего пользователя.
    """,
    responses={
        200: {
            'description': 'Статус заметки успешно изменен',
            'content': {
                'application/json': {
                    'example': {
                        **NOTE_EXAMPLE,
                        'is_completed': True,
                    },
                }
            },
        },
        401: AUTH_ERROR_RESPONSE,
        404: NOTE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def update_note_status_item(
    status_data: NoteStatusUpdate,
    current_user_id: CurrentUserIdDependency,
    note_id: int = Path(description='ID заметки', gt=0),
) -> NoteRead:
    note = await update_note_status(
        note_id=note_id,
        status_data=status_data,
        user_id=current_user_id,
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Note not found',
        )

    await _invalidate_notes_cache(current_user_id)
    return NoteRead.model_validate(note)


@core_router.delete(
    '/{note_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить заметку',
    description="""
    Удаление заметки текущего пользователя.

    **Проверки:**
    - Заметка должна существовать
    - Заметка должна принадлежать текущему пользователю

    **Результат:**
    При успешном удалении эндпоинт возвращает `204 No Content`.
    """,
    responses={
        204: {
            'description': 'Заметка успешно удалена',
        },
        401: AUTH_ERROR_RESPONSE,
        404: NOTE_NOT_FOUND_RESPONSE,
        422: VALIDATION_ERROR_RESPONSE,
    },
)
async def delete_note_item(
    current_user_id: CurrentUserIdDependency,
    note_id: int = Path(description='ID заметки', gt=0),
) -> None:
    is_deleted = await delete_note(
        note_id=note_id,
        user_id=current_user_id,
    )
    if not is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Note not found',
        )

    await _invalidate_notes_cache(current_user_id)
