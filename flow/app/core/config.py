from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# noinspection DuplicatedCode
class CoreSettings(BaseSettings):
    """Настройки конфигурации базы данных."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file_encoding='utf8',
        extra='ignore',
    )


class DatabaseSettings(CoreSettings):
    """Настройки конфигурации базы данных."""

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


class RedisSettings(CoreSettings):
    """Настройки конфигурации брокера сообщений Redis."""

    REDIS_HOST: str = 'localhost'
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def redis_url(self) -> str:
        """URL для подключения к базе Redis."""
        return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'


class Settings(CoreSettings):
    """Общие настройки конфигурации проекта."""

    db_settings: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis_settings: RedisSettings = RedisSettings()

    # 🔐 Добавляем параметры шифрования, общие с сервисом Tasks
    SECRET_KEY: str = 'test_secret_key_for_tests_only_32chars_min'
    JWT_ALGORITHM: str = 'HS256'


settings = Settings()
