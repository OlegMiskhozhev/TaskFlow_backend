"""Интеграционные тесты HTTP API заметок."""

from datetime import date

import pytest
from httpx import AsyncClient

from models.flow import Note


@pytest.mark.asyncio
async def test_create_note_returns_201_and_created_entity(
    test_client: AsyncClient,
    notes_api_prefix: str,
) -> None:
    """Проверяет успешное создание заметки через POST /notes/."""
    response = await test_client.post(
        f'{notes_api_prefix}/',
        json={'content': 'Интеграционная заметка', 'note_date': '2026-05-11'},
    )

    body = response.json()
    assert response.status_code == 201
    assert body['content'] == 'Интеграционная заметка'
    assert body['note_date'] == '2026-05-11'
    assert body['is_completed'] is False
    assert body['id'] > 0


@pytest.mark.asyncio
async def test_create_note_returns_422_for_invalid_body(
    test_client: AsyncClient,
    notes_api_prefix: str,
) -> None:
    """Проверяет тело ошибки 422 при невалидном payload создания."""
    response = await test_client.post(
        f'{notes_api_prefix}/',
        json={'content': '', 'note_date': '2026-05-11'},
    )

    body = response.json()
    assert response.status_code == 422
    assert body['detail'][0]['loc'] == ['body', 'content']


@pytest.mark.asyncio
async def test_get_notes_list_supports_filter_pagination_and_user_isolation(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """
    Проверить список заметок.

    Включая фильтрацию, пагинацию и изоляцию пользователя.
    """
    await note_factory(
        user_id=own_user_id, content='A', note_date=date(2026, 5, 12)
    )
    await note_factory(
        user_id=own_user_id, content='B', note_date=date(2026, 5, 12)
    )
    await note_factory(
        user_id=own_user_id, content='C', note_date=date(2026, 5, 13)
    )
    await note_factory(
        user_id=foreign_user_id, content='FOREIGN', note_date=date(2026, 5, 12)
    )

    filtered_response = await test_client.get(
        f'{notes_api_prefix}/',
        params={'note_date': '2026-05-12'},
    )
    paged_response = await test_client.get(
        f'{notes_api_prefix}/',
        params={'offset': 1, 'limit': 1},
    )

    filtered_notes = filtered_response.json()['notes']
    paged_notes = paged_response.json()['notes']

    assert filtered_response.status_code == 200
    assert [note['content'] for note in filtered_notes] == ['A', 'B']
    assert all(note['content'] != 'FOREIGN' for note in filtered_notes)
    assert paged_response.status_code == 200
    assert len(paged_notes) == 1


@pytest.mark.asyncio
async def test_get_notes_list_returns_422_for_invalid_query(
    test_client: AsyncClient,
    notes_api_prefix: str,
) -> None:
    """Проверяет тело ошибки 422 для невалидного query параметра limit."""
    response = await test_client.get(
        f'{notes_api_prefix}/', params={'limit': 0}
    )

    body = response.json()
    assert response.status_code == 422
    assert body['detail'][0]['loc'] == ['query', 'limit']


@pytest.mark.asyncio
async def test_get_note_returns_200_for_own_and_404_for_foreign_and_missing(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет получение своей заметки и 404 для чужой/несуществующей."""
    own = await note_factory(
        user_id=own_user_id, content='OWN', note_date=date(2026, 5, 14)
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='FOREIGN',
        note_date=date(2026, 5, 14),
    )

    own_response = await test_client.get(f'{notes_api_prefix}/{own.id}')
    foreign_response = await test_client.get(
        f'{notes_api_prefix}/{foreign.id}'
    )
    missing_response = await test_client.get(f'{notes_api_prefix}/999999')

    assert own_response.status_code == 200
    assert own_response.json()['content'] == 'OWN'
    assert foreign_response.status_code == 404
    assert foreign_response.json() == {'detail': 'Note not found'}
    assert missing_response.status_code == 404
    assert missing_response.json() == {'detail': 'Note not found'}


@pytest.mark.asyncio
async def test_get_note_returns_422_for_invalid_path_param(
    test_client: AsyncClient,
    notes_api_prefix: str,
) -> None:
    """Проверяет 422 и loc для невалидного note_id в path."""
    response = await test_client.get(f'{notes_api_prefix}/0')

    body = response.json()
    assert response.status_code == 422
    assert body['detail'][0]['loc'] == ['path', 'note_id']


@pytest.mark.asyncio
async def test_patch_note_empty_and_forbidden_404(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет PATCH без полей, обновление и 404 для чужой заметки."""
    own = await note_factory(
        user_id=own_user_id,
        content='Before patch',
        note_date=date(2026, 5, 15),
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='Foreign patch',
        note_date=date(2026, 5, 15),
    )

    empty_patch_response = await test_client.patch(
        f'{notes_api_prefix}/{own.id}', json={}
    )
    update_response = await test_client.patch(
        f'{notes_api_prefix}/{own.id}',
        json={'content': 'After patch', 'note_date': '2026-05-16'},
    )
    foreign_response = await test_client.patch(
        f'{notes_api_prefix}/{foreign.id}',
        json={'content': 'HACK'},
    )

    assert empty_patch_response.status_code == 200
    assert empty_patch_response.json()['content'] == 'Before patch'
    assert update_response.status_code == 200
    assert update_response.json()['content'] == 'After patch'
    assert update_response.json()['note_date'] == '2026-05-16'
    assert foreign_response.status_code == 404
    assert foreign_response.json() == {'detail': 'Note not found'}


@pytest.mark.asyncio
async def test_patch_note_status_updates_flag_and_returns_404_for_foreign(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
    foreign_user_id: int,
) -> None:
    """Проверяет PATCH /status для своей и чужой заметок."""
    own = await note_factory(
        user_id=own_user_id,
        content='Status own',
        note_date=date(2026, 5, 17),
        is_completed=False,
    )
    foreign = await note_factory(
        user_id=foreign_user_id,
        content='Status foreign',
        note_date=date(2026, 5, 17),
        is_completed=False,
    )

    own_response = await test_client.patch(
        f'{notes_api_prefix}/{own.id}/status',
        json={'is_completed': True},
    )
    foreign_response = await test_client.patch(
        f'{notes_api_prefix}/{foreign.id}/status',
        json={'is_completed': True},
    )

    assert own_response.status_code == 200
    assert own_response.json()['is_completed'] is True
    assert foreign_response.status_code == 404
    assert foreign_response.json() == {'detail': 'Note not found'}


@pytest.mark.asyncio
async def test_delete_note_returns_204_and_404_for_repeated_delete(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
    test_session_maker,
) -> None:
    """Проверяет удаление заметки и отсутствие записи в БД."""
    own = await note_factory(
        user_id=own_user_id,
        content='Delete me',
        note_date=date(2026, 5, 18),
    )

    delete_response = await test_client.delete(f'{notes_api_prefix}/{own.id}')
    second_delete_response = await test_client.delete(
        f'{notes_api_prefix}/{own.id}'
    )

    async with test_session_maker() as verify_session:
        deleted_note = await verify_session.get(Note, own.id)

    assert delete_response.status_code == 204
    assert second_delete_response.status_code == 404
    assert second_delete_response.json() == {'detail': 'Note not found'}
    assert deleted_note is None


@pytest.mark.asyncio
async def test_calendar_and_notes_by_date_endpoints_return_200(
    test_client: AsyncClient,
    notes_api_prefix: str,
    note_factory,
    own_user_id: int,
) -> None:
    """Проверяет GET /calendar и GET /date/{note_date} на корректные ответы."""
    await note_factory(
        user_id=own_user_id, content='Calendar 1', note_date=date(2026, 5, 19)
    )
    await note_factory(
        user_id=own_user_id, content='Calendar 2', note_date=date(2026, 5, 19)
    )

    calendar_response = await test_client.get(
        f'{notes_api_prefix}/calendar',
        params={'month': 5, 'year': 2026},
    )
    by_date_response = await test_client.get(
        f'{notes_api_prefix}/date/2026-05-19'
    )

    assert calendar_response.status_code == 200
    assert calendar_response.json()[0] == {
        'date': '2026-05-19',
        'notes_count': 2,
    }
    assert by_date_response.status_code == 200
    assert len(by_date_response.json()['notes']) == 2


@pytest.mark.asyncio
async def test_unauthorized_requests_return_401_with_expected_body(
    unauthorized_test_client: AsyncClient,
    notes_api_prefix: str,
) -> None:
    """Проверяет 401 для ручек, где требуется current_user_id."""
    endpoints = [
        ('get', f'{notes_api_prefix}/'),
        ('get', f'{notes_api_prefix}/calendar'),
        ('get', f'{notes_api_prefix}/date/2026-05-20'),
        (
            'post',
            f'{notes_api_prefix}/',
            {'content': 'x', 'note_date': '2026-05-20'},
        ),
        ('get', f'{notes_api_prefix}/1'),
        ('patch', f'{notes_api_prefix}/1', {'content': 'x'}),
        ('patch', f'{notes_api_prefix}/1/status', {'is_completed': True}),
        ('delete', f'{notes_api_prefix}/1'),
    ]

    for method, url, *payload in endpoints:
        kwargs = {'json': payload[0]} if payload else {}
        response = await getattr(unauthorized_test_client, method)(
            url, **kwargs
        )
        assert response.status_code == 401
        assert response.json() == {'detail': 'Invalid or expired access token'}
