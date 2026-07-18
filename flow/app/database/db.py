from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)

from core.config import settings

engine = create_async_engine(url=settings.db_settings.db_url)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

P = ParamSpec('P')
R = TypeVar('R')


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для моделей данных."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Автоматически формирует имя таблицы в базе из имени модели."""
        return cls.__name__.lower() + 's'


def connection(method: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Декоратор для подключения к базе данных и выполнения операций."""

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with async_session_maker() as session:
            try:
                return await method(*args, session=session, **kwargs)  # type: ignore[arg-type]
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    return wrapper
