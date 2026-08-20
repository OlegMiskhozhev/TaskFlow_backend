from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

AUTH_ERROR_DETAIL = 'Invalid or expired access token'

security = HTTPBearer(auto_error=False)


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
    """Верифицирует access JWT в памяти и возвращает id пользователя."""
    if token_data is None:
        raise _auth_error()

    try:
        payload = jwt.decode(
            token_data.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        user_id = payload.get('user_id')
        if user_id is None:
            raise _auth_error()

        return int(user_id)

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError) as e:
        raise _auth_error() from e


CurrentUserIdDependency = Annotated[int, Depends(get_current_user_id)]
