from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from core.config import settings

AUTH_ERROR_DETAIL = 'Invalid or expired access token'

security = HTTPBearer(auto_error=False)


class CurrentUserResponse(BaseModel):
    """Минимальный ответ tasks с идентификатором текущего пользователя."""

    id: int


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=AUTH_ERROR_DETAIL,
    )


async def get_current_user_id(
    token_data: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
) -> int:
    """Проверяет access JWT в tasks и возвращает id текущего пользователя."""
    if token_data is None:
        raise _auth_error()

    try:
        async with httpx.AsyncClient(
            timeout=settings.TASKS_AUTH_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(
                settings.TASKS_USER_ID_URL,
                headers={'Authorization': f'Bearer {token_data.credentials}'},
            )
    except httpx.HTTPError as e:
        raise _auth_error() from e

    if response.status_code != status.HTTP_200_OK:
        raise _auth_error()

    try:
        current_user = CurrentUserResponse.model_validate(response.json())
    except (ValueError, ValidationError) as e:
        raise _auth_error() from e

    return current_user.id


CurrentUserIdDependency = Annotated[int, Depends(get_current_user_id)]
