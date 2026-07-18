import redis
from celery import Celery
from celery import Task as CeleryTask
from celery.schedules import crontab
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings

# celery worker
celery_app = Celery(
    'TaskFlow',
    broker=settings.redis_settings.redis_url,
    backend=settings.redis_settings.redis_url,
    include=['beat.tasks', 'beat.auth_tasks'],
)


class BaseDbTask(CeleryTask):
    """Базовый класс для тасок Celery с единой инициализацией СУБД и Redis."""

    def __init__(self) -> None:
        super().__init__()
        # Инициализация ресурсов строго 1 раз на уровне воркера
        self.engine = create_engine(
            settings.db_settings.db_url.replace('+asyncpg', '')
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.redis_sync = redis.Redis.from_url(
            settings.redis_settings.redis_url, decode_responses=True
        )


# celery beat
celery_app.conf.beat_schedule = {
    'schedule_reminders': {
        'task': 'beat.tasks.send_reminder_task',
        'schedule': crontab(),
    },
    'task_start_reminders': {
        'task': 'beat.tasks.send_start_task_reminder',
        'schedule': crontab(),
    },
    'deadline_coming': {
        'task': 'beat.tasks.send_deadline_coming_reminder',
        'schedule': crontab(minute='*/1'),
    },
    'overdue_task': {
        'task': 'beat.tasks.send_overdue_task_reminder',
        'schedule': crontab(minute='*/1'),
    },
    'cleanup_inactive_tokens': {
        'task': 'beat.auth_tasks.cleanup_inactive_tokens_task',
        'schedule': crontab(minute='*/5'),
    },
    'auto_unlock_users': {
        'task': 'beat.auth_tasks.unlock_expired_users',
        'schedule': crontab(minute='*/1'),
    },
}
