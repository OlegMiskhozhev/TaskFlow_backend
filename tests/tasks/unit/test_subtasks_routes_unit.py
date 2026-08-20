import pytest
from fastapi import status

from routers.subtask import create_subtask, delete_subtask, update_subtask
from schemas.subtasks import SubtaskCreate, SubtaskUpdate


@pytest.mark.asyncio
class TestCreateSubtaskUnit:
    """Юнит-тесты для роутера создания подзадачи."""

    async def test_create_subtask_model_dump_and_add(
        self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: упаковка task_id в словарь и вызов базового service.add."""
        # 🚀 Вызываем нашу новую супер-фабрику
        mock_add = mock_crud_factory(router_path='subtask', method_name='add')
        mock_objects = mock_objects_factory(user_id=123, task_id=456)

        subtask_model = SubtaskCreate(name='Test Subtask')

        response = await create_subtask(
            objects=mock_objects, subtask_model=subtask_model
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        # Безопасно извлекаем позиционные аргументы
        args = mock_add.call_args.args

        # args[0] — это класс Subtask, args[1] — переданный dict данных
        assert args[0].__name__ == 'Subtask'
        assert args[1]['name'] == 'Test Subtask'
        assert args[1]['task_id'] == 456


@pytest.mark.asyncio
class TestUpdateSubtaskUnit:
    """Юнит-тесты для роутера частичного обновления подзадачи."""

    async def test_update_subtask_calls_service(
            self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: вызов service.update с корректными kwargs параметрами."""
        mock_update = mock_crud_factory(
            router_path='subtask', method_name='update'
        )
        mock_objects = mock_objects_factory(subtask_id=777, user_id=123)

        subtask_update = SubtaskUpdate(name='Updated Subtask')
        response = await update_subtask(
            objects=mock_objects, subtask_update=subtask_update
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once()

        call_kwargs = mock_update.call_args.kwargs

        assert call_kwargs['model'].__name__ == 'Subtask'
        assert call_kwargs['values']['id'] == 777
        assert call_kwargs['values']['name'] == 'Updated Subtask'


@pytest.mark.asyncio
class TestDeleteSubtaskUnit:
    """Юнит-тесты для роутера каскадного удаления подзадачи."""

    async def test_delete_subtask_calls_service(
        self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """
        Тест: вызов базового CRUD service.delete с передачей ID подзадачи.
        """
        mock_delete = mock_crud_factory(
            router_path='subtask', method_name='delete'
        )
        mock_objects = mock_objects_factory(subtask_id=999, user_id=123)

        response = await delete_subtask(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        # Извлекаем позиционные аргументы вызова CRUD-удаления
        args = mock_delete.call_args.args
        assert args[0].__name__ == 'Subtask'
        assert args[1] == 999
