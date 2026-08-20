from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.auth import (
    login,
    logout,
    recovery_password,
    register,
    reset_password,
    update_tokens,
)
from schemas.users import PasswordRequest, RecoveryRequest, RegisterRequest


@pytest.mark.asyncio
class TestRegisterUnit:
    """Юнит-тесты изолированной логики эндпоинта регистрации."""

    async def test_register_new_user_success(self, mocker):
        """Тест: успешная регистрация нового активного пользователя."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mock_add = mocker.patch(
            'routers.auth.service.add',
            new_callable=AsyncMock,
        )
        mock_token = mocker.patch(
            'services.auth.JwtService.create_confirmation_token',
            new_callable=AsyncMock,
        )
        mock_email = mocker.patch(
            'routers.auth.send_confirmation_email_task.delay'
        )

        mock_get_user.return_value = None
        mock_token.return_value = 'mock_confirm_token'
        mock_add.return_value = mocker.Mock(id=1, is_active=False)

        request = RegisterRequest(
            email='new@test.com',
            password='Test123!^*Test',
            confirm_password='Test123!^*Test',
        )

        result = await register(request)
        assert 'Вы успешно прошли регистрацию' in result['message']
        mock_add.assert_called_once()
        mock_email.assert_called_once_with(
            'new@test.com', 'mock_confirm_token'
        )

    async def test_register_existing_active_user_fails(self, mocker):
        """Тест: существующий активный пользователь выдает 400 по ТЗ."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mock_get_user.return_value = mocker.Mock(is_active=True)

        request = RegisterRequest(
            email='existing@test.com',
            password='NewTest123!^*Test',
            confirm_password='NewTest123!^*Test',
        )

        with pytest.raises(HTTPException) as exc:
            await register(request)

        assert exc.value.status_code == 400

    async def test_register_inactive_user_creates_new_token(self, mocker):
        """Тест: неактивный юзер получает новый токен без дублирования."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mocker.patch(
            'routers.auth.service.add',
            new_callable=AsyncMock,
        )
        mock_token = mocker.patch(
            'services.auth.JwtService.create_confirmation_token',
            new_callable=AsyncMock,
        )
        mock_email = mocker.patch(
            'routers.auth.send_confirmation_email_task.delay'
        )

        mock_user = mocker.Mock(is_active=False, id=1)
        mock_get_user.return_value = mock_user
        mock_token.return_value = 'new_confirm_token'

        request = RegisterRequest(
            email='inactive@test.com',
            password='Test123!^*Test',
            confirm_password='Test123!^*Test',
        )

        result = await register(request)
        assert 'Вы успешно прошли регистрацию' in result['message']
        mock_email.assert_called_once_with(
            'inactive@test.com', 'new_confirm_token'
        )


@pytest.mark.asyncio
class TestLoginUnit:
    """Юнит-тесты изолированной логики эндпоинта аутентификации (Login)."""

    async def test_login_success(self, mocker):
        """Тест: успешный логин через диспетчер handle_login_attempt."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mocker.patch(
            'services.auth.AuthService.handle_login_attempt',
            new_callable=AsyncMock,
        )
        mock_tokens = mocker.patch(
            'services.auth.JwtService.create_token_pair',
            new_callable=AsyncMock,
        )

        mock_user = mocker.Mock(
            id=1, is_active=True, password='hashed_password'
        )
        mock_get_user.return_value = mock_user

        mock_tokens.return_value = {
            'access_token': 'access123',
            'refresh_token': 'refresh123',
        }

        result = await login(email='test@test.com', password='Test123!^*Test')

        # Проверяем атрибуты выходной Pydantic-модели TokensPair через точку
        assert result.access_token == 'access123'
        assert result.refresh_token == 'refresh123'

    async def test_login_invalid_credentials(self, mocker) -> None:
        """Тест: неверные учетные данные выдают 400."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mock_get_user.return_value = None

        with pytest.raises(HTTPException) as exc:
            await login(email='wrong@test.com', password='wrong')

        assert exc.value.status_code == 400
        assert exc.value.detail.get('msg') == 'Неверный логин или пароль.'


@pytest.mark.asyncio
class TestLogoutUnit:
    """Юнит-тесты изолированной логики выхода пользователя из системы.

    Проверяет успешное аннулирование JWT-токена сессии (Logout)
    и зачистку контекста авторизации в сетевом кэше.
    """

    async def test_logout_success(self, mocker):
        """Тест: успешный выход с деактивацией ORM-объекта Token."""
        mock_get_token = mocker.patch(
            'services.auth.JwtService.get_token_by_access',
            new_callable=AsyncMock,
        )
        mocker.patch(
            'services.auth.AuthService.deactivate_token_object',
            new_callable=AsyncMock,
        )

        mock_token_obj = mocker.Mock(id=1)
        mock_get_token.return_value = mock_token_obj

        result = await logout(
            user=mocker.Mock(), authorization='Bearer test_token'
        )

        assert result.status_code == 200

    async def test_logout_no_token(self, mocker):
        """Тест: выход с несуществующим токеном — все равно успех."""
        mock_get_token = mocker.patch(
            'services.auth.JwtService.get_token_by_access',
            new_callable=AsyncMock,
        )
        mock_get_token.return_value = None

        result = await logout(
            user=mocker.Mock(), authorization='Bearer invalid_token'
        )

        assert result.status_code == 200


@pytest.mark.asyncio
class TestRecoveryPasswordUnit:
    """Юнит-тесты изолированной логики восстановления пароля."""

    async def test_recovery_password_user_not_exists(self, mocker):
        """Тест ТЗ: несуществующий пользователь вызывает ошибку 400."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mock_email = mocker.patch(
            'routers.auth.send_password_reset_email_task.delay'
        )

        mock_get_user.return_value = None
        request = RecoveryRequest(email='nonexistent@test.com')

        with pytest.raises(HTTPException) as exc:
            await recovery_password(request)

        assert exc.value.status_code == 400

        detail_dict = exc.value.detail
        assert detail_dict.get('msg') == (
            'Пользователь с указанными данными не зарегистрирован.'
        )
        mock_email.assert_not_called()

    async def test_recovery_password_success(self, mocker):
        """Тест: успешная генерация токена сброса и отправка email."""
        mock_get_user = mocker.patch(
            'routers.auth.get_user_by_email',
            new_callable=AsyncMock,
        )
        mock_token = mocker.patch(
            'services.auth.JwtService.create_password_recovery_token',
            new_callable=AsyncMock,
        )
        mock_email = mocker.patch(
            'routers.auth.send_password_reset_email_task.delay'
        )

        mock_user = mocker.Mock(id=1, is_active=True)
        mock_get_user.return_value = mock_user
        mock_token.return_value = 'mock_recovery_token'

        request = RecoveryRequest(email='active@test.com')
        result = await recovery_password(request)

        assert result is not None
        mock_email.assert_called_once_with(
            'active@test.com', 'mock_recovery_token'
        )


@pytest.mark.asyncio
class TestResetPasswordUnit:
    """Юнит-тесты изолированной логики сброса пароля (Reset)."""

    async def test_reset_password_success(self, mocker):
        """Тест: успешная смена пароля."""
        mock_hash = mocker.patch(
            'services.auth.CryptoService.hash_password',
            new_callable=AsyncMock,
        )
        mocker.patch(
            'routers.auth.service.update',
            new_callable=AsyncMock,
        )

        mock_hash.return_value = 'new_hashed_password'

        result = await reset_password(
            password_data=PasswordRequest(
                password='NewTest123!^*Test',
                confirm_password='NewTest123!^*Test',
            ),
            user=mocker.Mock(id=1),
        )

        assert result.status_code == 200


@pytest.mark.asyncio
class TestRefreshTokenUnit:
    """Юнит-тесты изолированной логики эндпоинта обновления токенов."""

    async def test_refresh_token_success(self, mocker):
        """Тест: активный токен — деактивация и выдача новой пары."""
        mock_verify = mocker.patch(
            'services.auth.JwtService.verify_token_payload',
            new_callable=AsyncMock,
        )
        mock_get_token = mocker.patch(
            'services.auth.JwtService.get_token_by_refresh',
            new_callable=AsyncMock,
        )
        mocker.patch(
            'services.auth.AuthService.deactivate_token_object',
            new_callable=AsyncMock,
        )
        mock_create = mocker.patch(
            'services.auth.JwtService.create_token_pair',
            new_callable=AsyncMock,
        )

        mock_verify.return_value = True
        mock_token_obj = mocker.Mock(id=1, user_id=2, is_active=True)
        mock_get_token.return_value = mock_token_obj

        # Передаем словарь под распаковку **tokens_data в ручке
        mock_create.return_value = {
            'access_token': 'new_access',
            'refresh_token': 'new_refresh',
        }

        result = await update_tokens(refresh_token='valid_refresh')

        # Проверяем поля возвращаемой Pydantic-схемы через точку
        assert result.access_token == 'new_access'
        assert result.refresh_token == 'new_refresh'

    async def test_refresh_token_invalid_signature(self, mocker):
        """Тест: невалидная подпись токена выдает 410 по вашему ТЗ."""
        mock_verify = mocker.patch(
            'services.auth.JwtService.verify_token_payload',
            new_callable=AsyncMock,
        )
        mock_verify.side_effect = HTTPException(status_code=401)

        with pytest.raises(HTTPException) as exc:
            await update_tokens(refresh_token='invalid_signature')

        assert exc.value.status_code == 401

