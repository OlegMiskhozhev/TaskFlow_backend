"""Unit-тесты Pydantic-схем модуля flow."""

from datetime import date

import pytest
from pydantic import ValidationError

from schemas.flow import (
    MAX_NOTE_CONTENT_LENGTH,
    CalendarNoteDate,
    NoteCreate,
    NoteStatusUpdate,
    NoteUpdate,
)


@pytest.fixture
def valid_note_create_payload() -> dict[str, str]:
    return {
        'content': 'Подготовить отчет',
        'note_date': '2026-05-07',
    }


@pytest.fixture
def valid_note_update_cases() -> list[
    tuple[dict[str, str], str | None, date | None]
]:
    return [
        ({}, None, None),
        ({'content': 'Обновить описание'}, 'Обновить описание', None),
        ({'note_date': '2026-05-08'}, None, date(2026, 5, 8)),
    ]


def test_note_create_valid_payload(
    valid_note_create_payload: dict[str, str],
) -> None:
    """Проверяет успешную валидацию NoteCreate с корректными данными."""
    payload = valid_note_create_payload

    note = NoteCreate.model_validate(payload)

    assert note.content == payload['content']
    assert note.note_date == date(2026, 5, 7)


def test_note_create_invalid_payload() -> None:
    """Проверяет обязательные ошибки валидации NoteCreate по полю loc."""
    cases = [
        ({'content': '', 'note_date': '2026-05-07'}, ('content',)),
        (
            {
                'content': 'x' * (MAX_NOTE_CONTENT_LENGTH + 1),
                'note_date': '2026-05-07',
            },
            ('content',),
        ),
        ({'content': 'Заметка', 'note_date': 'not-a-date'}, ('note_date',)),
    ]

    for payload, expected_loc in cases:
        with pytest.raises(ValidationError) as exc_info:
            NoteCreate.model_validate(payload)

        assert exc_info.value.errors()[0]['loc'] == expected_loc


def test_note_update_valid_payloads(
    valid_note_update_cases: list[
        tuple[dict[str, str], str | None, date | None]
    ],
) -> None:
    """Проверяет обязательные валидные сценарии NoteUpdate."""
    for payload, expected_content, expected_date in valid_note_update_cases:
        note = NoteUpdate.model_validate(payload)

        assert note.content == expected_content
        assert note.note_date == expected_date


def test_note_update_rejects_invalid_content() -> None:
    """Проверяет ошибки валидации контента NoteUpdate по полю loc."""
    cases = [
        ({'content': ''}, ('content',)),
        ({'content': 'x' * (MAX_NOTE_CONTENT_LENGTH + 1)}, ('content',)),
    ]

    for payload, expected_loc in cases:
        with pytest.raises(ValidationError) as exc_info:
            NoteUpdate.model_validate(payload)

        assert exc_info.value.errors()[0]['loc'] == expected_loc


def test_note_status_update_accepts_boolean_values() -> None:
    """Проверяет, что NoteStatusUpdate принимает True и False."""
    for value in (True, False):
        status = NoteStatusUpdate.model_validate({'is_completed': value})

        assert status.is_completed is value


def test_calendar_note_date_validation() -> None:
    """Проверяет alias date и populate_by_name для CalendarNoteDate."""
    cases = [
        ({'date': '2026-05-09', 'notes_count': 3}, date(2026, 5, 9), 3),
        ({'note_date': '2026-05-10', 'notes_count': 5}, date(2026, 5, 10), 5),
    ]

    for payload, expected_date, expected_count in cases:
        calendar_note = CalendarNoteDate.model_validate(payload)

        assert calendar_note.note_date == expected_date
        assert calendar_note.notes_count == expected_count


def test_calendar_note_date_dump_uses_alias() -> None:
    """Проверяет, что model_dump(by_alias=True) возвращает ключ date."""
    calendar_note = CalendarNoteDate.model_validate(
        {'note_date': '2026-05-11', 'notes_count': 2}
    )

    dumped = calendar_note.model_dump(by_alias=True)

    assert dumped['date'] == date(2026, 5, 11)
    assert dumped['notes_count'] == 2
    assert 'note_date' not in dumped
