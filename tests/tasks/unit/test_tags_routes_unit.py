import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from routers.tags import add_tag, get_tags, update_tag, update_task_tags
from schemas.tags import TagCreate, TagList, TagUpdate, TaskTags


@pytest.mark.asyncio
class TestAddTagUnit:
    """Юнит-тесты для роутера создания тега пользователя."""

    async def test_add_tag_model_dump_and_add(
        self, mock_user_factory, mock_crud_factory
    ) -> None:
        """Тест: успешный маппинг user_id и вызов базового service.add."""
        # 🚀 ИСПРАВЛЕНО: Явно указали путь к роутеру тегов
        mock_add = mock_crud_factory(router_path='tags', method_name='add')
        mock_user = mock_user_factory(user_id=42)

        tags_data = TagCreate(name='Test Tag')

        response = await add_tag(user=mock_user, tags_data=tags_data)

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        args = mock_add.call_args.args
        called_values = args[1]

        assert args[0].__name__ == 'Tag'
        assert called_values['name'] == 'Test Tag'
        assert called_values['user_id'] == 42


    async def test_add_tag_integrity_error_handling(
        self, mock_user_factory, mock_crud_factory
    ) -> None:
        """Тест: перехват дубликата тега и выдача плоского 409 JSON."""

        mock_add = mock_crud_factory(
            router_path='tags',
            method_name='add',
            side_effect=IntegrityError('Duplicate', {}, Exception()),
        )
        mock_user = mock_user_factory(user_id=42)
        tags_data = TagCreate(name='Duplicate Tag')

        with pytest.raises(HTTPException) as exc:
            await add_tag(user=mock_user, tags_data=tags_data)

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert exc.value.detail.get('msg') == (
            'Тег с таким названием уже существует.'
        )
        mock_add.assert_called_once()


@pytest.mark.asyncio
class TestUpdateTagUnit:
    """Юнит-тесты для роутера изменения названия тега."""

    async def test_update_tag_model_dump_and_update(
        self, mock_user_factory, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: добавление id тега в словарь обновления СУБД."""
        mock_update = mock_crud_factory(
            router_path='tags', method_name='update'
        )
        mock_user = mock_user_factory(user_id=123)

        # Вытаскиваем контекст, где сидит наш tag.id = 777
        mock_context = mock_objects_factory(tag_id=777)
        mock_tag = mock_context.tag

        tag_data = TagUpdate(name='Updated Tag')

        response = await update_tag(
            user=mock_user, tag=mock_tag, tag_data=tag_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once()

        args = mock_update.call_args.args
        called_model = args[0]
        called_values = args[1]

        assert called_model.__name__ == 'Tag'
        assert called_values['id'] == 777
        assert called_values['name'] == 'Updated Tag'


@pytest.mark.asyncio
class TestGetTagsUnit:
    """Юнит-тесты для роутера поисковой выборки тегов."""

    async def test_get_tags_calls_search_tags(self, mock_user_factory, mocker):
        """Тест: вызов поискового сервиса с query-параметрами."""
        mock_search = mocker.patch(
            'routers.tags.search_tags',
            return_value=[],
            new_callable=mocker.AsyncMock,
        )
        mock_user = mock_user_factory(user_id=123)

        result = await get_tags(user=mock_user, q='backend')

        assert isinstance(result, TagList)
        assert result.tags == []
        mock_search.assert_called_once_with(
            user_id=123, search_param='backend'
        )


@pytest.mark.asyncio
class TestUpdateTaskTagsUnit:
    """Юнит-тесты для роутера изменения связей тегов и задачи."""

    async def test_update_task_tags_calls_set_task_tags(
        self, mock_user_factory, mock_objects_factory, mocker
    ):
        """Тест: вызов set_task_tags с валидной Pydantic-моделью из ТЗ."""
        mock_set = mocker.patch(
            'routers.tags.set_task_tags',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(task_id=999)
        mock_user = mock_user_factory(user_id=123)

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
