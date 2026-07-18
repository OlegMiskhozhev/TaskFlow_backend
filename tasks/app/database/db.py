from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

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

engine = create_async_engine(url=settings.db_settings.db_url, echo=True)
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


def connection(
    method: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Декоратор для подключения к базе данных и выполнения операций."""

    @wraps(method)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with async_session_maker() as session:
            try:
                return await method(*args, session=session, **kwargs)
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    return wrapper
