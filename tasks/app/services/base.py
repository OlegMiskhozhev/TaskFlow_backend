from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import Base, connection

ModelT = TypeVar('ModelT', bound=Base)


class Service:
    """Базовый класс управлениями данными в базе."""

    @connection
    async def get(
        self, model: type[ModelT], obj_id: int, session: AsyncSession
    ) -> type[ModelT] | None:
        """Возвращает объект модели по его id."""
        item = await session.get(model, obj_id)
        return item if item else None

    @connection
    async def add(
        self, model: type[ModelT], values: dict, session: AsyncSession
    ) -> type[ModelT]:
        """Метод добавления записи в таблицу."""
        new_item = model(**values)
        session.add(new_item)
        try:
            await session.commit()
            await session.refresh(new_item)
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        return new_item

    @connection
    async def update(
        self, model: type[ModelT], values: dict, session: AsyncSession
    ) -> type[ModelT] | None:
        """Метод обновления записи в таблице."""
        item = await session.get(model, values.pop('id'))
        if item:
            for field, value in values.items():
                setattr(item, field, value)
            await session.commit()
            return item
        return None

    @connection
    async def delete(
        self, model: type[ModelT], obj_id: int, session: AsyncSession
    ) -> bool:
        """Метод удаления записи из таблицы."""
        item = await session.get(model, obj_id)
        if item:
            await session.delete(item)
            await session.commit()
            return True
        return False


service = Service()
