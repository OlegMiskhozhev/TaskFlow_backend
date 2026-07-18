import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.users import User
from services.base import service


@pytest.mark.asyncio
class TestServiceIntegration:
    """Интеграционные тесты базового CRUD-слоя СУБД (BaseService)."""

    async def test_add_integration(self, db_session):
        """Тест: добавление записи в PostgreSQL через базовый сервис."""
        user_data = {
            'email': 'add_test@test.com',
            'password': 'hash123',
            'timezone': 'UTC',
            'is_active': True,
            'username': 'adduser',
            'role': 'USER',
            'is_blocked': False,
        }

        new_user = await service.add(User, user_data)

        assert new_user is not None
        assert new_user.id is not None

        # Изолируем сессию для жесткой проверки физической записи
        await db_session.close()

        stmt = select(User).where(User.email == 'add_test@test.com')
        result = await db_session.execute(stmt)
        db_user = result.scalar_one_or_none()

        assert db_user is not None
        assert db_user.email == 'add_test@test.com'

    async def test_get_integration(self, db_session, create_test_user_factory):
        """Тест: получение записи по первичному ключу ID."""
        created_user = await create_test_user_factory(
            email='get_test@test.com', username='getuser'
        )
        user_id = created_user.id

        # Отсоединяем объект перед входом в метод с декоратором @connection
        db_session.expunge(created_user)

        user = await service.get(User, user_id)

        assert user is not None
        assert user.id == user_id
        assert user.email == 'get_test@test.com'

    async def test_get_not_found_integration(self, db_session):
        """Тест: извлечение несуществующего ID возвращает None."""
        user = await service.get(User, 99999)
        assert user is None

    async def test_update_integration(
        self, db_session, create_test_user_factory
    ):
        """Тест: обновление полей существующей записи."""
        created_user = await create_test_user_factory(
            email='update_test@test.com', username='updateuser'
        )
        user_id = created_user.id

        db_session.expunge(created_user)

        update_data = {
            'id': user_id,
            'username': 'updated_username',
            'email': 'updated@test.com',
        }

        updated_user = await service.update(User, update_data)

        assert updated_user is not None
        assert updated_user.username == 'updated_username'
        assert updated_user.email == 'updated@test.com'

        # Закрываем сессию теста для полной вычистки ОЗУ
        await db_session.close()

        stmt = select(User).where(User.id == user_id)
        result = await db_session.execute(stmt)
        db_user = result.scalar_one_or_none()
        assert db_user.username == 'updated_username'

    async def test_update_not_found_integration(self, db_session):
        """Тест: обновление несуществующей записи возвращает None."""
        update_data = {'id': 99999, 'username': 'new_name'}
        result = await service.update(User, update_data)
        assert result is None

    async def test_delete_integration(
        self, db_session, create_test_user_factory
    ):
        """Тест: каскадное удаление записи из таблицы БД."""
        created_user = await create_test_user_factory(
            email='delete_test@test.com', username='deleteuser'
        )
        user_id = created_user.id

        db_session.expunge(created_user)

        deleted = await service.delete(User, user_id)
        assert deleted is True

        await db_session.close()

        stmt = select(User).where(User.id == user_id)
        result = await db_session.execute(stmt)
        db_user = result.scalar_one_or_none()
        assert db_user is None

    async def test_delete_not_found_integration(self, db_session):
        """Тест: удаление отсутствующего ID возвращает False."""
        result = await service.delete(User, 99999)
        assert result is False

    async def test_add_rollback_on_error_integration(
        self, db_session, create_test_user_factory
    ):
        """Тест: автоматический откат транзакции при ошибке уникальности."""
        await create_test_user_factory(
            email='duplicate@test.com', username='dupuser'
        )

        user_data = {
            'email': 'duplicate@test.com',
            'password': 'hash456',
            'timezone': 'UTC',
            'is_active': True,
            'username': 'dupuser2',
            'role': 'USER',
            'is_blocked': False,
        }

        with pytest.raises(IntegrityError):
            await service.add(User, user_data)
