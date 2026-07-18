"""Unit-тесты зависимости аутентификации текущего пользователя."""

import httpx
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from core.config import settings
from core.dependency import AUTH_ERROR_DETAIL, get_current_user_id


class _MockResponse:
    """Упрощенный мок HTTP-ответа для тестов зависимости."""

    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._json_error = json_error

    def json(self) -> dict:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _MockAsyncClient:
    """Мок httpx.AsyncClient с управляемым ответом и ошибками."""

    response: _MockResponse = _MockResponse(status_code=200, payload={'id': 1})
    request_error: httpx.HTTPError | None = None
    captured_timeout: float | None = None

    def __init__(self, timeout: float) -> None:
        self.__class__.captured_timeout = timeout

    async def __aenter__(self) -> '_MockAsyncClient':
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str]) -> _MockResponse:
        _ = (url, headers)
        if self.__class__.request_error is not None:
            raise self.__class__.request_error
        return self.__class__.response


@pytest.fixture(autouse=True)
def _patch_dependency_httpx_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Подменяет httpx.AsyncClient в зависимости на управляемый мок."""
    monkeypatch.setattr('core.dependency.httpx.AsyncClient', _MockAsyncClient)


@pytest.fixture(autouse=True)
def _reset_mock_async_client_state() -> None:
    """Сбрасывает состояние мок-клиента перед каждым тестом."""
    _MockAsyncClient.response = _MockResponse(
        status_code=200, payload={'id': 1}
    )
    _MockAsyncClient.request_error = None
    _MockAsyncClient.captured_timeout = None


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_without_credentials() -> None:
    """Возвращает 401, если credentials отсутствуют."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_returns_id_for_valid_tasks_response(
    auth_token: HTTPAuthorizationCredentials,
) -> None:
    """Возвращает id пользователя при валидном ответе tasks."""
    _MockAsyncClient.response = _MockResponse(
        status_code=200, payload={'id': 1}
    )

    user_id = await get_current_user_id(auth_token)

    assert user_id == 1
    assert (
        _MockAsyncClient.captured_timeout
        == settings.TASKS_AUTH_TIMEOUT_SECONDS
    )


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_non_200_status(
    auth_token: HTTPAuthorizationCredentials,
) -> None:
    """Возвращает 401, если tasks вернул не-200 статус."""
    _MockAsyncClient.response = _MockResponse(
        status_code=403, payload={'detail': 'forbidden'}
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(auth_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_httpx_error(
    auth_token: HTTPAuthorizationCredentials,
) -> None:
    """Возвращает 401 при сетевой ошибке или timeout в запросе к tasks."""
    _MockAsyncClient.request_error = httpx.TimeoutException('timeout')

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(auth_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_for_invalid_json(
    auth_token: HTTPAuthorizationCredentials,
) -> None:
    """Возвращает 401, если tasks прислал невалидный JSON."""
    _MockAsyncClient.response = _MockResponse(
        status_code=200,
        json_error=ValueError('invalid json'),
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(auth_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL


@pytest.mark.asyncio
async def test_get_current_user_id_raises_401_when_id_missing(
    auth_token: HTTPAuthorizationCredentials,
) -> None:
    """Возвращает 401, если в JSON нет обязательного поля id."""
    _MockAsyncClient.response = _MockResponse(status_code=200, payload={})

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(auth_token)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == AUTH_ERROR_DETAIL
