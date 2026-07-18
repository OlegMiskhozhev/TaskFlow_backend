from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import status

from models.enums import TaskListStatus
from routers.tasklist import (
    add_tasklist,
    delete_tasklist,
    sort_tasklists,
    update_tasklist,
)
from schemas.tasklist import (
    TaskListCreate,
    TaskListSortRequest,
    TaskListUpdate,
)


@pytest.mark.asyncio
class TestAddTasklistUnit:
    """Юнит-тесты для роутера создания списка задач."""

    @patch(
        'routers.tasklist.create_tasklist_business_logic',
        new_callable=AsyncMock,
    )
    async def test_add_tasklist_calls_business_logic(self, mock_logic):
        """Тест: вызов инкапсулированного сервиса логики создания."""
        mock_objects = Mock()
        mock_objects.project.id = 10
        mock_objects.project.user_id = 123

        tasklist_data = TaskListCreate(name='Test TaskList')

        response = await add_tasklist(
            objects=mock_objects, tasklist_data=tasklist_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        # Исправлено: синхронизировано с реальным словарем без status='ACTIVE'
        mock_logic.assert_called_once_with(
            project_id=10,
            tasklist_dict={'name': 'Test TaskList'},
        )


@pytest.mark.asyncio
class TestUpdateTasklistUnit:
    """Юнит-тесты для роутера изменения параметров списка задач."""

    @patch(
        'routers.tasklist.update_tasklist_business_logic',
        new_callable=AsyncMock,
    )
    async def test_update_tasklist_calls_business_logic(self, mock_logic):
        """Тест: передача словаря параметров в слой бизнес-логики."""
        mock_objects = Mock()
        mock_objects.tasklist.id = 777
        mock_objects.project.user_id = 123

        tasks_list_data = TaskListUpdate(name='Updated TaskList')

        response = await update_tasklist(
            objects=mock_objects, tasks_list_data=tasks_list_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            tasklist_id=777,
            update_dict={'name': 'Updated TaskList'},
        )

    @patch(
        'routers.tasklist.update_tasklist_business_logic',
        new_callable=AsyncMock,
    )
    async def test_update_tasklist_status_done_passes_status(self, mock_logic):
        """Тест: корректная передача статуса DONE для закрытия задач."""
        mock_objects = Mock()
        mock_objects.tasklist.id = 777
        mock_objects.project.user_id = 123

        tasks_list_data = TaskListUpdate(status=TaskListStatus.DONE)

        response = await update_tasklist(
            objects=mock_objects, tasks_list_data=tasks_list_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            tasklist_id=777,
            update_dict={'status': TaskListStatus.DONE},
        )


@pytest.mark.asyncio
class TestDeleteTasklistUnit:
    """Юнит-тесты для роутера удаления списка задач."""

    @patch('routers.tasklist.service.delete', new_callable=AsyncMock)
    async def test_delete_tasklist_calls_service(self, mock_delete):
        """Тест: вызов базового CRUD-метода СУБД с передачей ID."""
        mock_objects = Mock()
        mock_objects.tasklist.id = 888
        mock_objects.project.user_id = 123

        response = await delete_tasklist(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        # Исправлено AttributeError: читаем позиционный кортеж call_args[0]
        called_args = mock_delete.call_args[0]
        assert called_args[0].__name__ == 'TaskList'
        assert called_args[1] == 888


@pytest.mark.asyncio
class TestSortTasklistsUnit:
    """Юнит-тесты для роутера Drag-and-Drop сортировки списков."""

    @patch('routers.tasklist.reorder_tasklist', new_callable=AsyncMock)
    async def test_sort_tasklists_calls_reorder_tasklist(self, mock_reorder):
        """Тест: вызов реордера с правильным именем метода из кода."""
        mock_objects = Mock()
        mock_objects.project.user_id = 123

        sort_data = TaskListSortRequest(
            tasklist_id=5, new_previous_tasklist_id=3
        )

        response = await sort_tasklists(
            objects=mock_objects, sort_data=sort_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_reorder.assert_called_once_with(
            mock_objects.project,
            5,
            3,
        )
