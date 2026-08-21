"""Unit-тесты зависимости аутентификации текущего пользователя."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from core.config import settings
from core.dependency import AUTH_ERROR_DETAIL, get_current_user_id


def _create_test_token(
    payload: dict,
    secret: str = settings.SECRET_KEY,
    algorithm: str = settings.JWT_ALGORITHM,
) -> HTTPAuthorizationCredentials:
    """Вспомогательная фабрика для генерации тестовых JWT-токенов."""
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_without_credentials() -> None:
    """Возвращает 401, если credentials отсутствуют."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_returns_id_for_valid_token() -> None:
    """Возвращает id пользователя при валидной подписи и payload."""
    payload = {
        'user_id': 42,  # 🔥 ИСПРАВЛЕНО: Ключ совпадает с core/dependency.py
        'exp': datetime.now(UTC) + timedelta(minutes=15),
    }
    token = _create_test_token(payload)

    user_id = await get_current_user_id(token)

    assert user_id == 42


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_expired_token() -> None:
    """Возвращает 401, если время жизни JWT-токена истекло."""
    payload = {
        'user_id': 42,  # 🔥 ИСПРАВЛЕНО: Ключ совпадает с core/dependency.py
        'exp': datetime.now(UTC) - timedelta(minutes=15),
    }
    token = _create_test_token(payload)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_invalid_signature() -> None:
    """Возвращает 401, если токен подписан чужим секретным ключом."""
    payload = {
        'user_id': 42,  # 🔥 ИСПРАВЛЕНО: Ключ совпадает с core/dependency.py
        'exp': datetime.now(UTC) + timedelta(minutes=15),
    }
    token = _create_test_token(
        payload,
        secret='malicious_secret_key_32chars_minimum'
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_when_id_missing() -> None:
    """Возвращает 401, если в полезной нагрузке отсутствует поле user_id."""
    payload = {
        'exp': datetime.now(UTC) + timedelta(minutes=15),
    }
    token = _create_test_token(payload)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_non_integer_id() -> None:
    """Возвращает 401, если идентификатор невозможно привести к int."""
    payload = {
        'user_id': 'not_a_number',
        'exp': datetime.now(UTC) + timedelta(minutes=15),
    }
    token = _create_test_token(payload)

    with pytest.raises(HTTPException) as exc_info: # 🔥 ИСПРАВЛЕНО РЕГИСТР!
        await get_current_user_id(token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL
