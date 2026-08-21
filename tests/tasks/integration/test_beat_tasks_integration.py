from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from beat.tasks import (
    send_deadline_coming_reminder,
    send_overdue_task_reminder,
    send_reminder_task,
    send_start_task_reminder,
)
from models.enums import ReminderStatus, TaskStatus


class TestSendReminderTaskIntegration:
    """Интеграционные тесты планировщика отправки напоминаний."""

    async def test_send_reminder_task_sends_queued_reminders(
        self,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
        mocker,
    ):
        """Тест: успешная выборка напоминаний в очереди и отправка email."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        task = await create_custom_task_factory(test_user)
        past_time = datetime.now(UTC) - timedelta(hours=1)
        reminder = await create_test_reminder_factory(
            task_id=task.id, send_time=past_time.replace(tzinfo=None)
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive
        mock_self.format_task_context.return_value = {}

        send_reminder_task.run.__func__(mock_self)

        mock_send_email.assert_called_once()

        await db_session.refresh(reminder)
        assert reminder.status == ReminderStatus.SENT

    async def test_send_reminder_task_no_queued_reminders(
        self,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
        mocker,
    ):
        """Тест: напоминания из будущего игнорируются планировщиком."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        task = await create_custom_task_factory(test_user)
        future_time = datetime.now(UTC) + timedelta(hours=24)
        await create_test_reminder_factory(
            task_id=task.id, send_time=future_time.replace(tzinfo=None)
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive

        send_reminder_task.run.__func__(mock_self)

        mock_send_email.assert_not_called()


@pytest.mark.asyncio
class TestSendDeadlineComingReminderIntegration:
    """Интеграционные тесты для задачи send_deadline_coming_reminder."""

    async def test_deadline_coming_reminder_sends_email(
        self,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        mocker,  # Используем фикстуру вместо декоратора
    ):
        """Тест: успешная отправка email для дедлайна менее суток."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        deadline_time = datetime.now(UTC) + timedelta(hours=23)
        await create_custom_task_factory(
            test_user,
            status=TaskStatus.IN_PROGRESS,
            deadline=deadline_time.replace(tzinfo=None),
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive
        mock_self.format_task_context.return_value = {}

        send_deadline_coming_reminder.run.__func__(mock_self)

        mock_send_email.assert_called_once()

    async def test_deadline_coming_no_email_for_distant_deadline(
        self,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        mocker,  # Используем фикстуру вместо декоратора
    ):
        """Тест: если до дедлайна далеко, уведомление не отправляется."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        deadline_time = datetime.now(UTC) + timedelta(days=10)
        await create_custom_task_factory(
            test_user,
            status=TaskStatus.IN_PROGRESS,
            deadline=deadline_time.replace(tzinfo=None),
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive

        send_deadline_coming_reminder.run.__func__(mock_self)

        mock_send_email.assert_not_called()


@pytest.mark.asyncio
class TestSendOverdueTaskReminderIntegration:
    """Интеграционные тесты для задачи send_overdue_task_reminder."""

    async def test_overdue_reminder_sends_email(
        self,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        mocker,  # Используем фикстуру вместо декоратора
    ):
        """Тест: задача просрочена — планировщик успешно отправляет email."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        past_deadline = datetime.now(UTC) - timedelta(hours=1)
        await create_custom_task_factory(
            test_user,
            status=TaskStatus.IN_PROGRESS,
            deadline=past_deadline.replace(tzinfo=None),
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive
        mock_self.format_task_context.return_value = {}

        send_overdue_task_reminder.run.__func__(mock_self)

        mock_send_email.assert_called_once()


@pytest.mark.asyncio
class TestSendStartTaskReminderIntegration:
    """Интеграционные тесты для задачи send_start_task_reminder."""

    async def test_start_task_reminder_sends_email_and_activates(
        self,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        mocker,  # Используем фикстуру вместо декоратора
    ):
        """Тест: старт запланированной задачи, отправка email, смена status."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        past_start = datetime.now(UTC) - timedelta(hours=1)
        task = await create_custom_task_factory(
            test_user,
            status=TaskStatus.SCHEDULE,
            start_at=past_start.replace(tzinfo=None),
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive
        mock_self.format_task_context.return_value = {}

        send_start_task_reminder.run.__func__(mock_self)

        mock_send_email.assert_called_once()

        await db_session.refresh(task)
        assert task.status == TaskStatus.IN_PROGRESS

    async def test_start_task_reminder_no_email_for_future_start(
        self,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        mocker,  # Используем фикстуру вместо декоратора
    ):
        """Тест: старт запланирован на будущее — задача не активируется."""
        mock_send_email = mocker.patch(
            'core.email.EmailService.send_template_email'
        )

        future_start = datetime.now(UTC) + timedelta(hours=24)
        task = await create_custom_task_factory(
            test_user,
            status=TaskStatus.SCHEDULE,
            start_at=future_start.replace(tzinfo=None),
        )

        now_naive = datetime.now(UTC).replace(tzinfo=None)

        mock_self = MagicMock()
        mock_self.SessionLocal.return_value.__enter__.return_value = (
            sync_db_session
        )
        mock_self.get_now_naive_utc.return_value = now_naive

        send_start_task_reminder.run.__func__(mock_self)

        mock_send_email.assert_not_called()

        await db_session.refresh(task)
        assert task.status == TaskStatus.SCHEDULE
