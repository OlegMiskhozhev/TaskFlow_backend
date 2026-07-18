from celery import Task as CeleryTask
from sqlalchemy import delete, select

from beat.celery import BaseDbTask, celery_app
from core.config import settings
from core.email import email_service
from models.users import Token, User


@celery_app.task(
    base=BaseDbTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def cleanup_inactive_tokens_task(self: BaseDbTask) -> None:
    """Удалить неактивные токены из базы данных."""
    with self.engine.begin() as conn:
        conn.execute(delete(Token).where(Token.is_active.is_(False)))


@celery_app.task(
    base=BaseDbTask,
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def unlock_expired_users(self: BaseDbTask) -> None:
    """Раз в минуту находит и разблокирует пользователей по TTL Redis."""
    with self.SessionLocal() as session:
        query = select(User).where(User.is_blocked)
        blocked_users = session.execute(query).scalars().all()

        if not blocked_users:
            return

        has_updates = False
        for user in blocked_users:
            lock_key = f'locked_user:{user.email}'

            if not self.redis_sync.exists(lock_key):
                user.is_blocked = False
                has_updates = True

        if has_updates:
            session.commit()


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def send_confirmation_email_task(
    self: CeleryTask,
    to_email: str,
    token: str,
) -> None:
    """Отправить токен подтверждения регистрации."""
    confirmation_url = (
        f'{settings.HOST_URL}:{settings.HOST_PORT}/?token={token}'
    )

    email_service.send_template_email(
        to_email=to_email,
        subject='Подтверждение регистрации в сервисе TaskFlow',
        template_name='confirmation_email.html',
        context={'confirmation_url': confirmation_url},
    )


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def send_password_reset_email_task(
    self: CeleryTask,
    to_email: str,
    token: str,
) -> None:
    """Отправить токен восстановления пароля."""
    reset_url = (
        f'{settings.HOST_URL}:{settings.HOST_PORT}/reset-password/{token}'
    )

    email_service.send_template_email(
        to_email=to_email,
        subject='Восстановление пароля в сервисе TaskFlow',
        template_name='password_reset_email.html',
        context={'reset_url': reset_url},
    )
