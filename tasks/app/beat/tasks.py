from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# from models.users import User
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from beat.celery import BaseDbTask, celery_app
from core.email import email_service
from models.enums import ReminderStatus, TaskStatus
from models.taskflow import Project, Reminder, Task, TaskList


class BaseReminderTask(BaseDbTask):
    """Базовый класс для тасок Celery с единой инициализацией СУБД."""

    def get_now_naive_utc(self) -> datetime:
        """Получить текущее наивное UTC-время для синхронной СУБД."""
        return datetime.now(ZoneInfo('UTC')).replace(tzinfo=None)

    def format_task_context(self, task: Task) -> dict[str, str]:
        """Централизованное и безопасное форматирование контекста задачи."""
        user = task.tasklist.project.user
        tz = ZoneInfo(user.timezone.value)

        start_str = (
            task.start_at.astimezone(tz).strftime('%d.%m.%Y %H:%M')
            if task.start_at
            else 'Не установлено'
        )
        deadline_str = (
            task.deadline.astimezone(tz).strftime('%d.%m.%Y %H:%M')
            if task.deadline
            else 'Не установлено'
        )

        return {
            'task_name': task.name,
            'task_description': task.description or 'Нет описания',
            'task_start_at': start_str,
            'task_deadline': deadline_str,
        }


@celery_app.task(
    base=BaseReminderTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def send_reminder_task(self: BaseReminderTask) -> None:
    """Отправить созданное пользователем напоминание."""
    with self.SessionLocal() as session:
        now_utc = self.get_now_naive_utc()

        reminders = (
            session.execute(
                select(Reminder)
                .options(
                    joinedload(Reminder.task)
                    .joinedload(Task.tasklist)
                    .joinedload(TaskList.project)
                    .joinedload(Project.user)
                )
                .where(
                    Reminder.status == ReminderStatus.QUEUED,
                    Reminder.send_time <= now_utc,
                )
            )
            .scalars()
            .all()
        )

        for reminder in reminders:
            task = reminder.task
            user = task.tasklist.project.user
            context = self.format_task_context(task)

            email_service.send_template_email(
                to_email=user.email,
                subject='Напоминание по задаче',
                template_name='send_reminder.html',
                context=context,
            )
            reminder.status = ReminderStatus.SENT

        session.commit()


@celery_app.task(
    base=BaseReminderTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def send_deadline_coming_reminder(self: BaseReminderTask) -> None:
    """Отправить уведомление о приближении срока завершения задачи."""
    with self.SessionLocal() as session:
        now_utc = self.get_now_naive_utc()
        reminder_time = now_utc + timedelta(days=1)

        overdue_tasks = (
            session.execute(
                select(Task)
                .options(
                    joinedload(Task.tasklist)
                    .joinedload(TaskList.project)
                    .joinedload(Project.user)
                )
                .where(
                    Task.status == TaskStatus.IN_PROGRESS,
                    Task.deadline <= reminder_time,
                )
            )
            .scalars()
            .all()
        )

        for task in overdue_tasks:
            already_sent = session.query(
                select(Reminder.id)
                .where(
                    Reminder.task_id == task.id,
                    Reminder.status == ReminderStatus.SENT,
                    Reminder.send_time >= task.deadline - timedelta(days=1),
                )
                .exists()
            ).scalar()

            if not already_sent:
                user = task.tasklist.project.user
                context = self.format_task_context(task)

                email_service.send_template_email(
                    to_email=user.email,
                    subject='Приближается срок выполнения задачи TaskFlow',
                    template_name='deadline_coming_reminder.html',
                    context=context,
                )
                session.add(
                    Reminder(
                        task_id=task.id,
                        send_time=now_utc,
                        status=ReminderStatus.SENT,
                        was_read=False,
                    )
                )

        session.commit()


@celery_app.task(
    base=BaseReminderTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def send_overdue_task_reminder(self: BaseReminderTask) -> None:
    """Отправить уведомление о просроченной задаче по дедлайну."""
    with self.SessionLocal() as session:
        now_utc = self.get_now_naive_utc()

        overdue_tasks = (
            session.execute(
                select(Task)
                .options(
                    joinedload(Task.tasklist)
                    .joinedload(TaskList.project)
                    .joinedload(Project.user)
                )
                .where(
                    Task.status == TaskStatus.IN_PROGRESS,
                    Task.deadline <= now_utc,
                )
            )
            .scalars()
            .all()
        )

        for task in overdue_tasks:
            already_sent = session.query(
                select(Reminder.id)
                .where(
                    Reminder.task_id == task.id,
                    Reminder.status == ReminderStatus.SENT,
                    Reminder.send_time >= task.deadline,
                )
                .exists()
            ).scalar()

            if not already_sent:
                user = task.tasklist.project.user
                context = self.format_task_context(task)

                email_service.send_template_email(
                    to_email=user.email,
                    subject='Срок задачи истёк TaskFlow',
                    template_name='overdue_deadline_reminder.html',
                    context=context,
                )
                session.add(
                    Reminder(
                        task_id=task.id,
                        send_time=now_utc,
                        status=ReminderStatus.SENT,
                        was_read=False,
                    )
                )

        session.commit()


@celery_app.task(
    base=BaseReminderTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def send_start_task_reminder(self: BaseReminderTask) -> None:
    """Отправить напоминание о старте выполнения задачи."""
    with self.SessionLocal() as session:
        now_utc = self.get_now_naive_utc()

        tasks = (
            session.execute(
                select(Task)
                .options(
                    joinedload(Task.tasklist)
                    .joinedload(TaskList.project)
                    .joinedload(Project.user)
                )
                .where(
                    Task.status == TaskStatus.SCHEDULE,
                    Task.start_at <= now_utc,
                )
            )
            .scalars()
            .all()
        )

        for task in tasks:
            user = task.tasklist.project.user
            context = self.format_task_context(task)

            email_service.send_template_email(
                to_email=user.email,
                subject=f'Напоминание о старте задачи: {task.name}',
                template_name='start_task_reminder.html',
                context=context,
            )
            task.status = TaskStatus.IN_PROGRESS
            session.add(
                Reminder(
                    send_time=now_utc,
                    status=ReminderStatus.SENT,
                    was_read=False,
                    task_id=task.id,
                )
            )

        session.commit()
