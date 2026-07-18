from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from models.enums import ReminderPeriodic, ReminderStatus
from models.taskflow import Reminder
from schemas.reminders import CreateReminder, CurrentTask, UserReminders
from services.reminders import (
    delete_reminder_objects,
    get_user_reminders,
    update_task_reminders,
)


@pytest.mark.asyncio
class TestRemindersServiceIntegration:
    """Интеграционные тесты атомарных транзакций сервиса напоминаний."""

    async def test_delete_reminder_objects_clears_only_queued(
        self,
        db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
    ):
        """Тест: метод удаляет только запланированные (QUEUED) записи."""
        task = await create_custom_task_factory(test_user)
        task_id = task.id
        now_naive = datetime.now(UTC).replace(tzinfo=None)

        await create_test_reminder_factory(
            task_id=task_id, send_time=now_naive, status=ReminderStatus.QUEUED
        )
        await create_test_reminder_factory(
            task_id=task_id, send_time=now_naive, status=ReminderStatus.SENT
        )

        db_session.expunge(task)

        await delete_reminder_objects(task_id)

        await db_session.close()

        stmt = select(Reminder).where(Reminder.task_id == task_id)
        db_result = await db_session.execute(stmt)
        reminders = db_result.scalars().all()

        assert len(reminders) == 1
        assert reminders[0].status == ReminderStatus.SENT

    async def test_update_task_reminders_generates_chain(
        self, db_session, test_user, create_custom_task_factory
    ):
        """Тест: генерация цепочки ежедневных напоминаний DAILY в СУБД."""
        now = datetime.now(UTC)
        task = await create_custom_task_factory(
            test_user, deadline=now + timedelta(days=10)
        )
        task_id = task.id

        reminder_model = CreateReminder(
            reminder_date=(now + timedelta(days=1)).date(),
            reminder_periodic=ReminderPeriodic.DAILY,
        )
        reminder_model.task = CurrentTask.model_validate(task)

        db_session.expunge(task)

        await update_task_reminders(reminder_model)

        await db_session.close()

        stmt = select(Reminder).where(Reminder.task_id == task_id)
        db_result = await db_session.execute(stmt)
        reminders = db_result.scalars().all()

        assert len(reminders) > 0

    async def test_update_task_reminders_empty_dates_when_start_after_deadline(
        self, db_session, test_user, create_custom_task_factory
    ):
        """Тест ТЗ: схема блокирует даты старта напоминания позже дедлайна."""
        now = datetime.now(UTC)
        task = await create_custom_task_factory(
            test_user, deadline=now + timedelta(days=2)
        )

        # Исправлено: ТЗ-валидатор обязан выкинуть ValidationError при сборке
        with pytest.raises(ValidationError) as exc:
            reminder_model = CreateReminder(
                reminder_date=(now + timedelta(days=5)).date(),
                reminder_periodic=ReminderPeriodic.DAILY,
            )
            reminder_model.task = CurrentTask.model_validate(task)

        assert 'Напоминание не может быть позже дедлайна задачи.' in str(
            exc.value
        )

    async def test_get_user_reminders_returns_only_sent_notification_ribbon(
        self,
        db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
    ):
        """
        Тест: метод возвращает только отправленные напоминания пользователя.
        """
        task = await create_custom_task_factory(test_user)
        now_naive = datetime.now(UTC).replace(tzinfo=None)

        await create_test_reminder_factory(
            task_id=task.id, send_time=now_naive, status=ReminderStatus.SENT
        )
        await create_test_reminder_factory(
            task_id=task.id, send_time=now_naive, status=ReminderStatus.QUEUED
        )

        db_session.expunge(test_user)

        result = await get_user_reminders(test_user)

        assert isinstance(result, UserReminders)
        assert len(result.reminders) == 1
