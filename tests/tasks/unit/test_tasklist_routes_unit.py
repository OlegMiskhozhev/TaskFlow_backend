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

    async def test_add_tasklist_calls_business_logic(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: вызов инкапсулированного сервиса логики создания."""
        mock_logic = mocker.patch(
            'routers.tasklist.create_tasklist_business_logic',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(project_id=10, user_id=123)

        tasklist_data = TaskListCreate(name='Test TaskList')

        response = await add_tasklist(
            objects=mock_objects, tasklist_data=tasklist_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        # Используем лаконичный assert_called_once_with для плоских полей
        mock_logic.assert_called_once_with(
            project_id=10,
            tasklist_dict={'name': 'Test TaskList'},
        )


@pytest.mark.asyncio
class TestUpdateTasklistUnit:
    """Юнит-тесты для роутера изменения параметров списка задач."""

    async def test_update_tasklist_calls_business_logic(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: передача словаря параметров в слой бизнес-логики."""
        mock_logic = mocker.patch(
            'routers.tasklist.update_tasklist_business_logic',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(tasklist_id=777, user_id=123)

        tasks_list_data = TaskListUpdate(name='Updated TaskList')

        response = await update_tasklist(
            objects=mock_objects, tasks_list_data=tasks_list_data
        )

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            tasklist_id=777,
            update_dict={'name': 'Updated TaskList'},
        )

    async def test_update_tasklist_status_done_passes_status(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: корректная передача статуса DONE для закрытия задач."""
        mock_logic = mocker.patch(
            'routers.tasklist.update_tasklist_business_logic',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(tasklist_id=777, user_id=123)

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

    async def test_delete_tasklist_calls_service(
        self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: вызов базового CRUD-метода СУБД с передачей ID."""
        mock_delete = mock_crud_factory(
            router_path='tasklist', method_name='delete'
        )
        mock_objects = mock_objects_factory(tasklist_id=888, user_id=123)

        response = await delete_tasklist(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        # Современное безопасное извлечение позиционных аргументов
        called_args = mock_delete.call_args.args
        assert called_args[0].__name__ == 'TaskList'
        assert called_args[1] == 888


@pytest.mark.asyncio
class TestSortTasklistsUnit:
    """Юнит-тесты для роутера Drag-and-Drop сортировки списков."""

    async def test_sort_tasklists_calls_reorder_tasklist(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: вызов сервиса изменения порядка списков с параметрами."""
        mock_reorder = mocker.patch(
            'routers.tasklist.reorder_tasklist',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(user_id=123)

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
