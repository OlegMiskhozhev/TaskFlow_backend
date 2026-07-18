from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from models.users import Token, User
from services.auth import auth_service


@pytest.mark.asyncio
class TestAuthFunctionsIntegration:
    """Интеграционные тесты криптографии и хранения сессий токенов."""

    async def test_create_token_pair_integration(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест: реальное создание и валидация пары токенов."""
        user = await create_test_user_factory(
            email='pair_test@test.com', username='pair_user'
        )

        result = await auth_service.jwt.create_token_pair(user.id)

        access_payload = await auth_service.jwt.verify_token_payload(
            result['access_token'], 'access'
        )
        refresh_payload = await auth_service.jwt.verify_token_payload(
            result['refresh_token'], 'refresh'
        )

        assert access_payload['user_id'] == user.id
        assert refresh_payload['user_id'] == user.id

        token_obj = await auth_service.jwt.get_token_by_refresh(
            result['refresh_token']
        )
        assert token_obj is not None
        assert token_obj.access_token == result['access_token']
        assert token_obj.refresh_token == result['refresh_token']
        assert token_obj.is_active is True

    async def test_create_password_recovery_token_integration(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест создания токена восстановления пароля."""
        user = await create_test_user_factory(
            email='recovery_test@test.com', username='recovery_user'
        )

        token = await auth_service.jwt.create_password_recovery_token(user.id)

        payload = await auth_service.jwt.verify_token_payload(
            token, 'password_recovery'
        )

        assert payload['user_id'] == user.id
        assert payload['type'] == 'password_recovery'

        exp_timestamp = payload['exp']
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=UTC)
        expected_exp = datetime.now(UTC) + timedelta(minutes=15)

        assert abs((exp_datetime - expected_exp).total_seconds()) < 5

    async def test_deactivate_token_integration(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест деактивации сессии токена."""
        user = await create_test_user_factory(
            email='deactivate_test@test.com', username='deactivate_user'
        )

        result = await auth_service.jwt.create_token_pair(user.id)
        token_obj = await auth_service.jwt.get_token_by_refresh(
            result['refresh_token']
        )

        await auth_service.deactivate_token_object(token_obj)

        updated_token = await auth_service.jwt.get_token_by_refresh(
            result['refresh_token']
        )
        assert updated_token.is_active is False

    async def test_get_token_object_by_access_token_integration(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест получения токена по access_token."""
        user = await create_test_user_factory(
            email='access_test@test.com', username='access_user'
        )

        result = await auth_service.jwt.create_token_pair(user.id)
        token_obj = await auth_service.jwt.get_token_by_access(
            result['access_token']
        )

        assert token_obj is not None
        assert token_obj.access_token == result['access_token']
        assert token_obj.user_id == user.id

    async def test_get_token_object_by_refresh_token_integration(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест получения токена по refresh_token."""
        user = await create_test_user_factory(
            email='refresh_test@test.com', username='refresh_user'
        )

        result = await auth_service.jwt.create_token_pair(user.id)
        token_obj = await auth_service.jwt.get_token_by_refresh(
            result['refresh_token']
        )

        assert token_obj is not None
        assert token_obj.refresh_token == result['refresh_token']
        assert token_obj.user_id == user.id

    async def test_create_token_pair_mocked(
        self, db_session, create_test_user_factory
    ):
        """Интеграционный тест записи с моканием приватного кодировщика."""
        user = await create_test_user_factory(
            email='test@test.com', username='test_mocked', is_active=False
        )

        with patch('services.auth.JwtService._encode_token') as mock_encode:
            mock_encode.side_effect = [
                'mock_access_token',
                'mock_refresh_token',
            ]

            result = await auth_service.jwt.create_token_pair(user.id)

            assert result['access_token'] == 'mock_access_token'
            assert result['refresh_token'] == 'mock_refresh_token'

            stmt = select(Token).where(Token.user_id == user.id)
            db_result = await db_session.execute(stmt)
            token = db_result.scalar_one()

            assert token.access_token == 'mock_access_token'
            assert token.refresh_token == 'mock_refresh_token'
            assert token.is_active is True

    async def test_execute_db_lock_integration(
        self, db_session, create_test_user_factory
    ):
        """Тест: исполнительный метод брутфорса жестко блокирует юзера в БД."""
        # 1. Создаем пользователя, который изначально НЕ заблокирован
        user = await create_test_user_factory(
            email='locked_test@test.com', username='brute_target'
        )
        assert user.is_blocked is False

        # 2. Исправлено InvalidRequestError: отсоединяем юзера от сессии теста
        db_session.expunge(user)

        # 3. Вызываем внутренний атомарный метод принудительной блокировки
        await auth_service._execute_db_lock(user)

        # 4. Проверяем, что в PostgreSQL значение is_blocked перешло в True
        stmt = select(User).where(User.email == 'locked_test@test.com')
        db_result = await db_session.execute(stmt)
        updated_user = db_result.scalar_one()

        assert updated_user.is_blocked is True
