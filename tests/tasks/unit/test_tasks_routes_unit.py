from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

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

    @patch('routers.tasks.service.add', new_callable=AsyncMock)
    async def test_create_task_model_dump(self, mock_add):
        """Тест: упаковка tasklist_id в kwargs и вызов базового service.add."""
        mock_objects = Mock()
        mock_objects.project.user.timezone = Timezone.UTC
        mock_objects.project.user_id = 123
        mock_objects.tasklist.id = 10

        task_data = TaskCreate(name='Test Task')
        task_data.user_timezone = Timezone.UTC

        response = await create_task(
            objects=mock_objects, task_model=task_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_add.assert_called_once()

        # Синхронизировано под гибридную сигнатуру call(Task, values={...})
        assert mock_add.call_args[0][0] == Task

        call_values = mock_add.call_args.kwargs['values']
        assert call_values['name'] == 'Test Task'
        assert call_values['tasklist_id'] == 10


@pytest.mark.asyncio
class TestGetAndUpdateTaskUnit:
    """Юнит-тесты извлечения и частичного изменения полей задачи."""

    @patch('routers.tasks.get_task_detail', new_callable=AsyncMock)
    async def test_get_task_calls_service(self, mock_detail):
        """Тест: вызов детального сервисного слоя get_task_detail."""
        mock_detail.return_value = Mock()
        mock_objects = Mock()
        mock_objects.task = Mock()

        result = await get_task(objects=mock_objects)

        assert result is not None
        mock_detail.assert_called_once_with(mock_objects.task)

    @patch('routers.tasks.service.update', new_callable=AsyncMock)
    @patch('routers.tasks.get_task_detail', new_callable=AsyncMock)
    async def test_update_task_calls_service_and_detail(
        self, mock_detail, mock_update
    ):
        """Тест: изменение текстовых полей задачи через СУБД."""
        mock_task_obj = Mock()
        mock_task_obj.id = 777
        mock_task_obj.tasklist_id = 10
        mock_task_obj.name = 'Original Title'
        mock_task_obj.status = 'in_progress'
        mock_task_obj.priority = 'Средний'
        mock_task_obj.user_timezone = Timezone.UTC

        # Задаем будущие дедлайны для обхода бизнес-валидаторов времени
        mock_task_obj.created_at = datetime.now(UTC)
        mock_task_obj.start_at = datetime.now(UTC) + timedelta(days=5)
        mock_task_obj.deadline = datetime.now(UTC) + timedelta(days=10)
        mock_task_obj.tags = []
        mock_task_obj.subtasks = []
        mock_task_obj.attachments = []

        mock_objects = Mock()
        mock_objects.task = mock_task_obj
        mock_objects.project.user_id = 123
        mock_update.return_value = mock_task_obj

        task_update = TaskInfoUpdate(name='New Title')

        await update_task(objects=mock_objects, task_update=task_update)

        mock_update.assert_called_once()
        mock_detail.assert_called_once()

        # Исправлено: извлекаем словарь изменений из позиционного кортежа
        assert mock_update.call_args[0][0] == Task
        call_values = mock_update.call_args[0][1]
        assert call_values['name'] == 'New Title'
        assert call_values['id'] == 777


@pytest.mark.asyncio
class TestTaskPeriodAndStatusUnit:
    """Юнит-тесты ТЗ-ручек изменения дат и каскадного перевода статусов."""

    @patch('routers.tasks.service.update', new_callable=AsyncMock)
    @patch('routers.tasks.delete_reminder_objects', new_callable=AsyncMock)
    async def test_update_task_period_success(self, mock_delete, mock_update):
        """Тест: сброс настроек периодических напоминаний при смене дат."""
        mock_task_obj = Mock()
        mock_task_obj.id = 555
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

        mock_objects = Mock()
        mock_objects.task = mock_task_obj
        mock_objects.project.user.timezone = Timezone.UTC
        mock_objects.project.user_id = 123
        mock_objects.project.deadline = datetime.now(UTC) + timedelta(days=20)

        task_period = TaskPeriodUpdate()

        response = await update_task_period(
            objects=mock_objects, task_period=task_period
        )

        assert response.status_code == status.HTTP_200_OK
        mock_delete.assert_called_once_with(555)
        mock_update.assert_called_once()

        # Исправлено: читаем позиционный кортеж аргументов обновления СУБД
        assert mock_update.call_args[0][0] == Task
        call_values = mock_update.call_args[0][1]
        assert call_values['id'] == 555
        assert call_values['reminder_datetime'] is None
        assert call_values['reminder_periodic'] == ReminderPeriodic.NONE

    @patch(
        'routers.tasks.update_task_status_business_logic',
        new_callable=AsyncMock,
    )
    async def test_update_task_status_calls_business_logic(self, mock_logic):
        """Тест: вызов транзакционного каскада закрытия подзадач."""
        mock_task_obj = Mock()
        mock_task_obj.id = 333
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

        mock_objects = Mock()
        mock_objects.project.user_id = 123
        mock_objects.task = mock_task_obj

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

    @patch('routers.tasks.move_task_business_logic', new_callable=AsyncMock)
    async def test_move_task_calls_business_logic(self, mock_logic):
        """Тест: перенаправление параметров в слой move_task_business_logic."""
        mock_objects = Mock()
        mock_objects.task.id = 111
        mock_objects.project.id = 222
        mock_objects.project.user_id = 123

        move_data = TaskMove(tasklist_id=888)

        response = await move_task(objects=mock_objects, move_data=move_data)

        assert response.status_code == status.HTTP_200_OK
        mock_logic.assert_called_once_with(
            task_id=111,
            new_tasklist_id=888,
            current_project_id=222,
        )

    @patch('routers.tasks.service.delete', new_callable=AsyncMock)
    async def test_delete_task_success(self, mock_delete):
        """Тест: каскадное удаление карточки задачи через CRUD-сервис СУБД."""
        mock_objects = Mock()
        mock_objects.task.id = 999
        mock_objects.project.user_id = 123

        response = await delete_task(objects=mock_objects)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        # Сверяем именованные параметры удаления из kwargs
        call_kwargs = mock_delete.call_args.kwargs
        assert call_kwargs['model'] == Task
        assert call_kwargs['id'] == 999
