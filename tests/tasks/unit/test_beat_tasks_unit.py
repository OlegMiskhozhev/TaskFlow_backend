import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from beat.tasks import (
    send_deadline_coming_reminder,
    send_overdue_task_reminder,
    send_reminder_task,
    send_start_task_reminder,
)
from models.enums import ReminderStatus, TaskStatus


@pytest.fixture(scope='function')
def sync_db_session():
    """Синхронная фикстура сессии СУБД специально для Celery-тестов."""
    async_url = os.getenv('DATABASE_URL')
    if async_url:
        sync_url = async_url.replace('postgresql+asyncpg://', 'postgresql://')
    else:
        user = os.getenv('TASKS_DB_USER', 'postgres')
        password = os.getenv('TASKS_DB_PASSWORD', 'postgres')
        db_name = os.getenv('TASKS_DB', 'postgres')
        # Используем точное имя сервиса базы данных из docker-compose
        sync_url = (
            f'postgresql://{user}:{password}@tasks_db_test:5432/{db_name}'
        )

    engine = create_engine(sync_url, pool_pre_ping=True)
    SyncSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
class TestSendReminderTaskIntegration:
    """Юнит-тесты планировщика отправки напоминаний воркерами Celery."""

    @patch('core.email.EmailService.send_template_email')
    async def test_send_reminder_task_sends_queued_reminders(
        self,
        mock_send_email,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
    ):
        """Тест: успешная выборка QUEUED напоминаний и отправка email."""
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

        # Рефрешим объект через его родную асинхронную сессию
        await db_session.refresh(reminder)
        assert reminder.status == ReminderStatus.SENT

    @patch('core.email.EmailService.send_template_email')
    async def test_send_reminder_task_no_queued_reminders(
        self,
        mock_send_email,
        sync_db_session,
        test_user,
        create_custom_task_factory,
        create_test_reminder_factory,
    ):
        """Тест: напоминания из будущего игнорируются планировщиком."""
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
    """Юнит-тесты для задачи send_deadline_coming_reminder."""

    @patch('core.email.EmailService.send_template_email')
    async def test_deadline_coming_reminder_sends_email(
        self,
        mock_send_email,
        sync_db_session,
        test_user,
        create_custom_task_factory,
    ):
        """Тест: отправка email, если до дедлайна осталось менее суток."""
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

    @patch('core.email.EmailService.send_template_email')
    async def test_deadline_coming_no_email_for_distant_deadline(
        self,
        mock_send_email,
        sync_db_session,
        test_user,
        create_custom_task_factory,
    ):
        """Тест: если до дедлайна далеко, уведомление не шлется."""
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
    """Юнит-тесты для задачи send_overdue_task_reminder."""

    @patch('core.email.EmailService.send_template_email')
    async def test_overdue_reminder_sends_email(
        self,
        mock_send_email,
        sync_db_session,
        test_user,
        create_custom_task_factory,
    ):
        """Тест: задача просрочена — планировщик высылает алерт."""
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
    """Юнит-тесты для задачи send_start_task_reminder."""

    @patch('core.email.EmailService.send_template_email')
    async def test_start_task_reminder_sends_email_and_activates(
        self,
        mock_send_email,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
    ):
        """
        Тест: старт SCHEDULE задачи, отправка писем и перевод в IN_PROGRESS.
        """
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

    @patch('core.email.EmailService.send_template_email')
    async def test_start_task_reminder_no_email_for_future_start(
        self,
        mock_send_email,
        db_session,
        sync_db_session,
        test_user,
        create_custom_task_factory,
    ):
        """Тест: старт запланирован на завтра — задача не активируется."""
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
