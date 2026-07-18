import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Базовый класс конфигурации проекта."""

    model_config = SettingsConfigDict(
        env_file=os.path.join(Path.cwd().parent.parent, '.env'),
        env_file_encoding='utf8',
        extra='ignore',
    )


class DatabaseSettings(CoreSettings):
    """Настройки конфигурации базы данных."""

    TASKS_DB_USER: str
    TASKS_DB_PASSWORD: str
    TASKS_DB_HOST: str
    TASKS_DB_PORT: int
    TASKS_DB: str

    @property
    def db_url(self) -> str:
        """URL для подключения к базе данных."""
        return (
            f'postgresql+asyncpg://{self.TASKS_DB_USER}:'
            f'{self.TASKS_DB_PASSWORD}@'
            f'{self.TASKS_DB_HOST}:'
            f'{self.TASKS_DB_PORT}/'
            f'{self.TASKS_DB}'
        )


class EmailSettings(CoreSettings):
    """Настройки конфигурации доступа к электронной почте."""

    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str


class MinioSettings(CoreSettings):
    """Настройки конфигурации доступа к хранилищу файлов."""

    MINIO_URL: str
    MINIO_ROOT_USER: str
    MINIO_ROOT_PASSWORD: str


class RedisSettings(CoreSettings):
    """Настройки конфигурации брокера сообщений Redis."""

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int

    @property
    def redis_url(self) -> str:
        """URL для подключения к базе Redis."""
        return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'


class GoogleAuthSettings(CoreSettings):
    """Настройки для интеграции с Google OAuth2."""

    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str


class GitLabAuthSettings(CoreSettings):
    """Настройки для интеграции с GitLab OAuth2."""

    GITLAB_CLIENT_ID: str
    GITLAB_CLIENT_SECRET: str
    GITLAB_REDIRECT_URI: str


class Settings(CoreSettings):
    """Общие настройки конфигурации проекта."""

    db_settings: DatabaseSettings = DatabaseSettings()
    email_settings: EmailSettings = EmailSettings()
    minio_settings: MinioSettings = MinioSettings()
    redis_settings: RedisSettings = RedisSettings()
    google_settings: GoogleAuthSettings = GoogleAuthSettings()
    gitlab_settings: GitLabAuthSettings = GitLabAuthSettings()
    templates_dir: str = os.path.join(Path.cwd(), 'templates')
    HOST_URL: str
    HOST_PORT: str
    JWT_ALGORITHM: str
    SECRET_KEY: str
    LOGIN_MAX_ATTEMPTS: int = 5
    USER_LOCK_TIMEOUT: int = 3600
    ACCESS_TOKEN_LIFETIME_MINUTS: int = 30
    CONFIRM_TOKEN_LIFETIME_HOURS: int = 24
    REFRESH_TOKEN_LIFETIME_HOURS: int = 24
    AVATAR_ALLOWABLE_FILE_SIZE: int = 2 * 1024 * 1024  # 2 Mb
    ATTACHMENT_ALLOWABLE_FILE_SIZE: int = 10 * 1024 * 1024  # 10 Mb
    TOTAL_UPLOAD_LIMIT: int = 50 * 1024 * 1024  # 50 Mb
    AVATAR_ALLOWABLE_FILE_TYPE: list[str] = [
        'image/jpeg',
        'image/jpg',
        'image/png',
    ]
    ATTACHMENT_ALLOWABLE_FILE_TYPE: list[str] = [
        'image/jpeg',
        'image/jpg',
        'image/png',
        'text/plain',
        'application/msword',
        'application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ]
    DANGEROUS_EXTENSIONS: set[str] = {
        'exe',
        'dll',
        'bat',
        'cmd',
        'sh',
        'bash',
        'php',
        'phtml',
        'js',
        'py',
        'pl',
        'jsp',
        'asp',
        'aspx',
        'vbs',
    }
    FILE_ROUTES_CONFIG: dict[str, int] = {
        '/user/avatar': 2 * 1024 * 1024,
        '/projects/attachments/': 10 * 1024 * 1024,
    }


settings = Settings()
