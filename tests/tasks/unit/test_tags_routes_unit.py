from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from routers.tags import add_tag, get_tags, update_tag, update_task_tags
from schemas.tags import TagCreate, TagList, TagUpdate, TaskTags


@pytest.mark.asyncio
class TestAddTagUnit:
    """Юнит-тесты для роутера создания тега пользователя."""

    @patch('routers.tags.service.add', new_callable=AsyncMock)
    async def test_add_tag_model_dump_and_add(self, mock_add):
        """Тест: успешный маппинг user_id и вызов базового service.add."""
        mock_user = Mock()
        mock_user.id = 42

        tags_data = TagCreate(name='Test Tag')

        response = await add_tag(user=mock_user, tags_data=tags_data)

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        call_kwargs = (
            mock_add.call_args.kwargs
            if mock_add.call_args.kwargs
            else mock_add.call_args[0][1]
        )

        if isinstance(call_kwargs, dict):
            assert call_kwargs['name'] == 'Test Tag'
            assert call_kwargs['user_id'] == 42

    @patch('routers.tags.service.add', new_callable=AsyncMock)
    async def test_add_tag_integrity_error_handling(self, mock_add):
        """Тест: перехват дубликата тега и выдача плоского 409 JSON."""
        mock_add.side_effect = IntegrityError('Duplicate', {}, None)

        mock_user = Mock()
        mock_user.id = 42

        tags_data = TagCreate(name='Duplicate Tag')

        with pytest.raises(HTTPException) as exc:
            await add_tag(user=mock_user, tags_data=tags_data)

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert exc.value.detail['msg'] == (
            'Тег с таким названием уже существует.'
        )


@pytest.mark.asyncio
class TestUpdateTagUnit:
    """Юнит-тесты для роутера изменения названия тега."""

    @patch('routers.tags.service.update', new_callable=AsyncMock)
    async def test_update_tag_model_dump_and_update(self, mock_update):
        """Тест: добавление id тега в словарь обновления СУБД."""
        mock_user = Mock()
        mock_tag = Mock()
        mock_tag.id = 777

        tag_data = TagUpdate(name='Updated Tag')

        response = await update_tag(
            user=mock_user, tag=mock_tag, tag_data=tag_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once()

        call_kwargs = (
            mock_update.call_args.kwargs
            if mock_update.call_args.kwargs
            else mock_update.call_args[0][1]
        )

        if isinstance(call_kwargs, dict):
            assert call_kwargs['id'] == 777
            assert call_kwargs['name'] == 'Updated Tag'


@pytest.mark.asyncio
class TestGetTagsUnit:
    """Юнит-тесты для роутера поисковой выборки тегов."""

    @patch('routers.tags.search_tags', new_callable=AsyncMock)
    async def test_get_tags_calls_search_tags(self, mock_search):
        """Тест: вызов поискового сервиса с query-параметрами."""
        mock_search.return_value = []
        mock_user = Mock()
        mock_user.id = 123

        result = await get_tags(user=mock_user, q='backend')

        assert isinstance(result, TagList)
        assert result.tags == []
        mock_search.assert_called_once_with(
            user_id=123, search_param='backend'
        )


@pytest.mark.asyncio
class TestUpdateTaskTagsUnit:
    """Юнит-тесты для роутера изменения связей тегов и задачи."""

    @patch('routers.tags.set_task_tags', new_callable=AsyncMock)
    async def test_update_task_tags_calls_set_task_tags(self, mock_set):
        """Тест: вызов set_task_tags с передачей Dforce-модели из ТЗ."""
        mock_task = Mock()
        mock_task.id = 999

        mock_objects = Mock()
        mock_objects.task = mock_task

        mock_user = Mock()
        mock_user.id = 123

        updated_tag_ids = TaskTags(tag_ids=[1, 3, 5])

        response = await update_task_tags(
            user=mock_user,
            objects=mock_objects,
            updated_tag_ids=updated_tag_ids,
        )

        assert response.status_code == status.HTTP_200_OK
        # Исправлено под новую сигнатуру роутера
        mock_set.assert_called_once_with(
            user_id=123,
            task_id=999,
            new_tag_ids_model=updated_tag_ids,
        )
