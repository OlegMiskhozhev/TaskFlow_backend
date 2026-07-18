from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_PATH = Path.cwd().parent / '.env'
BASE_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=ENV_FILE_PATH,
    env_file_encoding='utf8',
    extra='ignore',
)


class DatabaseSettings(BaseSettings):
    """Настройки конфигурации базы данных."""

    model_config = BASE_SETTINGS_CONFIG

    FLOW_DB_USER: str
    FLOW_DB_PASSWORD: str
    FLOW_DB_HOST: str
    FLOW_DB_PORT: int
    FLOW_DB: str

    @property
    def db_url(self) -> str:
        """URL для подключения к базе данных."""
        return (
            f'postgresql+asyncpg://{self.FLOW_DB_USER}:'
            f'{self.FLOW_DB_PASSWORD}@'
            f'{self.FLOW_DB_HOST}:'
            f'{self.FLOW_DB_PORT}/'
            f'{self.FLOW_DB}'
        )


class Settings(BaseSettings):
    """Общие настройки конфигурации проекта."""

    model_config = BASE_SETTINGS_CONFIG

    db_settings: DatabaseSettings = Field(default_factory=DatabaseSettings)
    TASKS_USER_ID_URL: str = 'http://tasks_backend:8000/user/id'
    TASKS_AUTH_TIMEOUT_SECONDS: float = Field(default=3.0, gt=0)


settings = Settings()
