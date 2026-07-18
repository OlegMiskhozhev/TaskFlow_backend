from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status

from routers.subtask import create_subtask, delete_subtask, update_subtask
from schemas.subtasks import SubtaskCreate, SubtaskUpdate


@pytest.mark.asyncio
class TestCreateSubtaskUnit:
    """Юнит-тесты для роутера создания подзадачи."""

    @patch('routers.subtask.service.add', new_callable=AsyncMock)
    async def test_create_subtask_model_dump_and_add(self, mock_add):
        """Тест: упаковка task_id в словарь и вызов базового service.add."""
        mock_objects = Mock()
        mock_objects.task.id = 456
        mock_objects.project.user_id = 123

        subtask_model = SubtaskCreate(name='Test Subtask')

        response = await create_subtask(
            objects=mock_objects, subtask_model=subtask_model
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        # Извлекаем позиционные аргументы вызова CRUD-сервиса
        args = mock_add.call_args[0]

        # args[0] — это класс Subtask, args[1] — переданный dict данных
        assert args[0].__name__ == 'Subtask'
        assert args[1]['name'] == 'Test Subtask'
        assert args[1]['task_id'] == 456


@pytest.mark.asyncio
class TestUpdateSubtaskUnit:
    """Юнит-тесты для роутера частичного обновления подзазадачи."""

    @patch('routers.subtask.service.update', new_callable=AsyncMock)
    async def test_update_subtask_calls_service(self, mock_update):
        """Тест: вызов service.update с корректными kwargs параметрами."""
        mock_objects = Mock()
        mock_objects.subtask.id = 777
        mock_objects.project.user_id = 123

        subtask_update = SubtaskUpdate(name='Updated Subtask')

        response = await update_subtask(
            objects=mock_objects, subtask_update=subtask_update
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once()

        # Исправлено IndexError: извлекаем именованные параметры kwargs
        call_kwargs = mock_update.call_args.kwargs

        # Проверяем структуру вызова базового CRUD-сервиса
        assert call_kwargs['model'].__name__ == 'Subtask'
        assert call_kwargs['values']['id'] == 777
        assert call_kwargs['values']['name'] == 'Updated Subtask'


@pytest.mark.asyncio
class TestDeleteSubtaskUnit:
    """Юнит-тесты для роутера каскадного удаления подзадачи."""

    @patch('routers.subtask.service.delete', new_callable=AsyncMock)
    async def test_delete_subtask_calls_service(self, mock_delete):
        """
        Тест: вызов базового CRUD service.delete с передачей ID подзадачи.
        """
        mock_objects = Mock()
        mock_objects.subtask.id = 999
        mock_objects.project.user_id = 123

        response = await delete_subtask(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        # Извлекаем позиционные аргументы вызова CRUD-удаления
        args = mock_delete.call_args[0]
        assert args[0].__name__ == 'Subtask'
        assert args[1] == 999
