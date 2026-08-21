from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from models.enums import ReminderPeriodic
from routers.reminders import (
    delete_reminders,
    get_reminders,
    read_reminders,
    reminder_create,
)
from schemas.reminders import CreateReminder, ReminderUpdate


@pytest.mark.asyncio
class TestReminderCreateUnit:
    """Юнит-тесты для роутера создания и обновления цепочки напоминаний."""

    async def test_reminder_create_success(self, mocker):
        """Тест: успешная передача таймзоны и вызов сервиса генерации."""
        mock_update_task = mocker.patch(
            'routers.reminders.update_task_reminders',
            new_callable=mocker.AsyncMock
        )
        mock_task_obj = mocker.Mock()
        mock_task_obj.id = 10
        mock_task_obj.status = 'in_progress'

        future_deadline = datetime.now(UTC) + timedelta(days=10)
        mock_task_obj.deadline = future_deadline
        mock_task_obj.start_at = None

        mock_objects = mocker.Mock()
        mock_objects.project.user.timezone.value = 'Europe/Moscow'
        mock_objects.task = mock_task_obj

        future_date = (datetime.now(UTC) + timedelta(days=1)).date()

        reminder_model = CreateReminder(
            reminder_date=future_date,
            reminder_periodic=ReminderPeriodic.NONE,
        )

        response = await reminder_create(
            objects=mock_objects, reminder_model=reminder_model
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert reminder_model.user_timezone == 'Europe/Moscow'
        assert reminder_model.task.id == 10
        mock_update_task.assert_called_once_with(reminder_model)


@pytest.mark.asyncio
class TestGetRemindersUnit:
    """Юнит-тесты для роутера получения ленты напоминаний."""

    async def test_get_reminders_calls_service(
            self,
            mock_user_factory,
            mocker
    ):
        """Тест: вызов сервисного слоя get_user_reminders."""
        mock_get = mocker.patch(
            'routers.reminders.get_user_reminders',
            return_value=mocker.Mock(),
            new_callable=mocker.AsyncMock
        )
        mock_user = mock_user_factory()

        result = await get_reminders(current_user=mock_user)

        assert result is not None
        mock_get.assert_called_once_with(mock_user)


@pytest.mark.asyncio
class TestReadReminderUnit:
    """Юнит-тесты для роутера отметки прочтения напоминания."""

    async def test_read_reminder_model_dump_and_update(
        self,
        mock_reminder_factory,
        mocker
    ):
        """Тест: упаковка id в словарь и вызов базового service.update."""
        mock_update = mocker.patch(
            'routers.reminders.service.update',
            new_callable=mocker.AsyncMock,
        )
        mock_reminder = mock_reminder_factory(reminder_id=777)

        reminder_read = ReminderUpdate(was_read=True)

        response = await read_reminders(
            reminder=mock_reminder, reminder_read=reminder_read
        )

        assert response.status_code == status.HTTP_200_OK
        mock_update.assert_called_once()

        called_args = mock_update.call_args.args
        called_model = called_args[0]
        called_values = called_args[1]

        assert called_model.__name__ == 'Reminder'
        assert called_values['id'] == 777
        assert called_values['was_read'] is True


@pytest.mark.asyncio
class TestDeleteReminderUnit:
    """Юнит-тесты для роутера удаления напоминания."""

    async def test_delete_reminder_calls_service(
        self,
        mock_reminder_factory,
        mocker
    ):
        """Тест: вызов базового CRUD service.delete с нужным ID."""
        mock_delete = mocker.patch(
            'routers.reminders.service.delete',
            new_callable=mocker.AsyncMock
        )
        mock_reminder = mock_reminder_factory(reminder_id=888)

        response = await delete_reminders(reminder=mock_reminder)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_delete.assert_called_once()

        called_args = mock_delete.call_args.args
        called_model = called_args[0]
        called_id = called_args[1]

        # Проверяем, что в удаление ушла правильная сущность и её ID
        assert called_model.__name__ == 'Reminder'
        assert called_id == 888
