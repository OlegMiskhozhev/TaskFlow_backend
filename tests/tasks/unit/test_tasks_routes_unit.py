from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from models.enums import ReminderPeriodic, Timezone
from models.taskflow import Task
from routers.tasks import (
    create_task,
    delete_task,
    get_task,
    move_task,
    update_task,
    update_task_period,
    update_task_status,
)
from schemas.tasks import (
    TaskCreate,
    TaskInfoUpdate,
    TaskMove,
    TaskPeriodUpdate,
    TaskStatusUpdate,
)


@pytest.mark.asyncio
class TestCreateTaskUnit:
    """Юнит-тесты для роутера создания задачи."""

    async def test_create_task_model_dump(
        self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: упаковка tasklist_id в kwargs и вызов базового service.add."""
        mock_add = mock_crud_factory(router_path='tasks', method_name='add')
        mock_objects = mock_objects_factory(tasklist_id=10, user_id=123)
        mock_objects.project.user.timezone = Timezone.UTC

        task_data = TaskCreate(name='Test Task')
        task_data.user_timezone = Timezone.UTC

        response = await create_task(
            objects=mock_objects, task_model=task_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        # Позиционные аргументы извлекаем через .args
        args = mock_add.call_args.args
        assert args[0] == Task

        call_values = mock_add.call_args.kwargs['values']
        assert call_values['name'] == 'Test Task'
        assert call_values['tasklist_id'] == 10


@pytest.mark.asyncio
class TestGetAndUpdateTaskUnit:
    """Юнит-тесты извлечения и частичного изменения полей задачи."""

    async def test_get_task_calls_service(self, mocker) -> None:
        """Тест: вызов сервиса получения деталей задачи."""
        mock_detail = mocker.patch(
            'routers.tasks.get_task_detail',
            new_callable=mocker.AsyncMock,
            return_value=mocker.Mock(),
        )
        mock_objects = mocker.Mock()
        mock_objects.task = mocker.Mock()

        result = await get_task(objects=mock_objects)

        assert result is not None
        mock_detail.assert_called_once_with(mock_objects.task)

    async def test_update_task_calls_service_and_detail(
        self, mock_objects_factory, mock_crud_factory, mocker
    ) -> None:
        """Тест: изменение текстовых полей задачи через СУБД."""
        # 🚀 Использована фабрика контекста вместо 15 строк ручного забивания
        mock_objects = mock_objects_factory(task_id=777, user_id=123)
        mock_task_obj = mock_objects.task
        mock_task_obj.tasklist_id = 10
        mock_task_obj.name = 'Original Title'
        mock_task_obj.status = 'in_progress'
        mock_task_obj.priority = 'Средний'
        mock_task_obj.user_timezone = Timezone.UTC
        mock_task_obj.created_at = datetime.now(UTC)
        mock_task_obj.start_at = datetime.now(UTC) + timedelta(days=5)
        mock_task_obj.deadline = datetime.now(UTC) + timedelta(days=10)
        mock_task_obj.tags = []
        mock_task_obj.subtasks = []
        mock_task_obj.attachments = []

        mock_update = mock_crud_factory(
            router_path='tasks',
            method_name='update',
            return_value=mock_task_obj,
        )
        mock_detail = mocker.patch(
            'routers.tasks.get_task_detail',
            new_callable=mocker.AsyncMock,
        )

        task_update = TaskInfoUpdate(name='New Title')

        await update_task(objects=mock_objects, task_update=task_update)

        mock_update.assert_called_once()
        mock_detail.assert_called_once()

        args = mock_update.call_args.args
        assert args[0] == Task
        call_values = args[1]
        assert call_values['name'] == 'New Title'
        assert call_values['id'] == 777


@pytest.mark.asyncio
class TestTaskPeriodAndStatusUnit:
    """Юнит-тесты ТЗ-ручек изменения дат и каскадного перевода статусов."""

    async def test_update_task_period_success(
        self, mock_objects_factory, mock_crud_factory, mocker
    ) -> None:
        """Тест: сброс настроек напоминаний при смене дат задачи."""
        mock_objects = mock_objects_factory(task_id=555, user_id=123)
        mock_task_obj = mock_objects.task
        mock_task_obj.tasklist_id = 10
        mock_task_obj.name = 'Task Name'
        mock_task_obj.status = 'in_progress'
        mock_task_obj.priority = 'Средний'
        mock_task_obj.user_timezone = Timezone.UTC
        mock_task_obj.created_at = datetime.now(UTC)
        mock_task_obj.start_at = datetime.now(UTC) + timedelta(days=5)
        mock_task_obj.deadline = datetime.now(UTC) + timedelta(days=10)
        mock_task_obj.tags = []
        mock_task_obj.subtasks = []
        mock_task_obj.attachments = []

        mock_objects.project.user.timezone = Timezone.UTC
        mock_objects.project.deadline = datetime.now(UTC) + timedelta(days=20)

        mock_update = mock_crud_factory(
            router_path='tasks', method_name='update'
        )
        mock_delete = mocker.patch(
            'routers.tasks.delete_reminder_objects',
            new_callable=mocker.AsyncMock,
        )

        task_period = TaskPeriodUpdate()

        response = await update_task_period(
            objects=mock_objects, task_period=task_period
        )

        assert response.status_code == status.HTTP_200_OK
        mock_delete.assert_called_once_with(555)
        mock_update.assert_called_once()

        args = mock_update.call_args.args
        assert args[0] == Task
        call_values = args[1]
        assert call_values['id'] == 555
        assert call_values['reminder_datetime'] is None
        assert call_values['reminder_periodic'] == ReminderPeriodic.NONE

    async def test_update_task_status_calls_business_logic(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: вызов транзакционного каскада закрытия подзадач."""
        mock_logic = mocker.patch(
            'routers.tasks.update_task_status_business_logic',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(task_id=333, user_id=123)
        mock_task_obj = mock_objects.task
        mock_task_obj.tasklist_id = 10
        mock_task_obj.name = 'Task Name'
        mock_task_obj.status = 'in_progress'
        mock_task_obj.priority = 'Средний'
        mock_task_obj.user_timezone = Timezone.UTC
        mock_task_obj.created_at = datetime.now(UTC)
        mock_task_obj.start_at = datetime.now(UTC) + timedelta(days=5)
        mock_task_obj.deadline = datetime.now(UTC) + timedelta(days=10)
        mock_task_obj.tags = []
        mock_task_obj.subtasks = []
        mock_task_obj.attachments = []

        task_status = TaskStatusUpdate(status='done')

        response = await update_task_status(
            objects=mock_objects, task_status=task_status
        )

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            task_id=333,
            status_dict={'status': 'done'},
        )


@pytest.mark.asyncio
class TestMoveAndDeleteTaskUnit:
    """Юнит-тесты Drag-and-Drop перемещений и окончательного удаления."""

    async def test_move_task_calls_business_logic(
        self, mock_objects_factory, mocker
    ) -> None:
        """Тест: перенаправление параметров в слой изменения позиции."""
        mock_logic = mocker.patch(
            'routers.tasks.move_task_business_logic',
            new_callable=mocker.AsyncMock,
        )
        mock_objects = mock_objects_factory(task_id=111, user_id=123)
        mock_objects.project.id = 222

        move_data = TaskMove(tasklist_id=888)

        response = await move_task(objects=mock_objects, move_data=move_data)

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            task_id=111,
            new_tasklist_id=888,
            current_project_id=222,
        )

    async def test_delete_task_success(
        self, mock_objects_factory, mock_crud_factory
    ) -> None:
        """Тест: каскадное удаление карточки задачи через CRUD-сервис."""
        mock_delete = mock_crud_factory(
            router_path='tasks', method_name='delete'
        )
        mock_objects = mock_objects_factory(task_id=999, user_id=123)

        response = await delete_task(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        kwargs = mock_delete.call_args.kwargs
        assert kwargs['model'] == Task
        assert kwargs['obj_id'] == 999
