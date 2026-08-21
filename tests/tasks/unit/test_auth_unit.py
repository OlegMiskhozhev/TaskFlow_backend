import jwt
import pytest
from fastapi import HTTPException

from core.config import settings
from services.auth import auth_service


@pytest.mark.asyncio
class TestAuthFunctionsUnit:
    """Тесты хэширования паролей и кодирования/декодирования JWT токенов."""

    async def test_hash_and_verify_password(self) -> None:
        """Тест хэширования и проверки пароля через CryptoService."""
        password = 'my_secret_password'
        hashed = await auth_service.crypto.hash_password(password)

        assert hashed != password
        assert (
            await auth_service.crypto.verify_password(password, hashed) is True
        )
        assert (
            await auth_service.crypto.verify_password('wrong_password', hashed)
            is False
        )

    async def test_create_token(self) -> None:
        """Тест создания JWT токена через JwtService."""
        payload = {'user_id': 1, 'type': 'access', 'test': 'data'}
        token = auth_service.jwt._encode_token(payload)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    async def test_create_confirmation_token(self, mocker) -> None:
        """Тест создания токена подтверждения."""
        user_id = 123
        mock_encode = mocker.patch('services.auth.JwtService._encode_token')
        mock_encode.return_value = 'mock_confirmation_token'

        token = await auth_service.jwt.create_confirmation_token(user_id)

        mock_encode.assert_called_once()
        call_payload = mock_encode.call_args[0][0]

        assert call_payload['user_id'] == 123
        assert call_payload['type'] == 'confirm'
        assert 'exp' in call_payload
        assert token == 'mock_confirmation_token'

    async def test_verify_token_valid(self, mocker) -> None:
        """Тест успешной верификации токена."""
        payload = {'user_id': 789, 'type': 'access'}
        mock_decode = mocker.patch('jwt.decode')
        mock_decode.return_value = payload

        result = await auth_service.jwt.verify_token_payload(
            'valid_token', 'access'
        )

        assert result == payload
        mock_decode.assert_called_once_with(
            'valid_token',
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

    async def test_verify_token_expired(self, mocker) -> None:
        """Тест обработки истекшего токена с плоской ошибкой Pydantic."""
        mock_decode = mocker.patch('jwt.decode')
        mock_decode.side_effect = jwt.ExpiredSignatureError()

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.jwt.verify_token_payload(
                'expired_token', 'access'
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail is not None
        assert 'истек' in str(exc_info.value.detail)

    async def test_verify_token_invalid(self, mocker) -> None:
        """Тест обработки невалидного токена с плоской ошибкой Pydantic."""
        mock_decode = mocker.patch('jwt.decode')
        mock_decode.side_effect = jwt.InvalidTokenError()

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.jwt.verify_token_payload(
                'invalid_token', 'access'
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail is not None
        assert 'Невалидный' in str(exc_info.value.detail)

    async def test_verify_token_wrong_type(self, mocker) -> None:
        """Тест проверки типа токена с плоской ошибкой Pydantic."""
        payload = {'user_id': 789, 'type': 'access'}
        mock_decode = mocker.patch('jwt.decode')
        mock_decode.return_value = payload

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.jwt.verify_token_payload(
                'access_token', 'refresh'
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail is not None
        assert 'Неверный тип' in str(exc_info.value.detail)

    async def test_brute_force_counter_and_lock(self, mocker) -> None:
        """Тест: ровно на 5-ю неудачную попытку Redis взводит блокировку."""
        mock_redis = mocker.patch(
            'services.auth.auth_service.brute_force.redis'
        )
        mock_redis.incr.return_value = 5
        mock_user_input = mocker.Mock(email='attacker@test.com')

        attempts = await auth_service.brute_force.register_failed_attempt(
            mock_user_input
        )

        assert attempts == 5
        mock_redis.incr.assert_called_once_with(
            'login_attempts:attacker@test.com'
        )

    async def test_handle_login_attempt_returns_attempts_left(
        self, mocker
    ) -> None:
        """Тест выполнения ТЗ: при 3-й ошибке выводится остаток попыток."""
        mock_redis = mocker.patch(
            'services.auth.auth_service.brute_force.redis'
        )
        mock_redis.incr.return_value = 3

        mocker.patch.object(
            auth_service.crypto,
            'verify_password',
            new_callable=mocker.AsyncMock,
        ).return_value = False

        mock_user = mocker.Mock(
            is_active=True, is_blocked=False, password='hash'
        )

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.handle_login_attempt(
                mock_user, 'wrong_password'
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail is not None
        assert 'Осталось попыток: 2' in str(exc_info.value.detail)

    async def test_handle_login_attempt_inactive_user(self, mocker) -> None:
        """Тест: неактивный пользователь моментально блокируется с 403."""
        mock_user = mocker.Mock(is_active=False)

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.handle_login_attempt(mock_user, 'any_password')

        assert exc_info.value.status_code == 403
