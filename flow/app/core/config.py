from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_SETTINGS_CONFIG = SettingsConfigDict(
    env_file_encoding='utf8',
    extra='ignore',
)


class DatabaseSettings(BaseSettings):
    """Настройки конфигурации базы данных."""

    model_config = BASE_SETTINGS_CONFIG

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: int
    POSTGRES_HOST: str = 'localhost'

    @property
    def db_url(self) -> str:
        """URL для подключения к базе данных."""
        return (
            f'postgresql+asyncpg://{self.POSTGRES_USER}:'
            f'{self.POSTGRES_PASSWORD}@'
            f'{self.POSTGRES_HOST}:'
            f'{self.POSTGRES_PORT}/'
            f'{self.POSTGRES_DB}'
        )


class Settings(BaseSettings):
    """Общие настройки конфигурации проекта."""

    model_config = BASE_SETTINGS_CONFIG

    db_settings: DatabaseSettings = Field(default_factory=DatabaseSettings)
    TASKS_USER_ID_URL: str = 'http://tasks_backend:8000/user/id'
    TASKS_AUTH_TIMEOUT_SECONDS: float = Field(default=3.0, gt=0)


settings = Settings()
