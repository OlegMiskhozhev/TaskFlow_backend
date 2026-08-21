from typing import Annotated
from urllib.parse import unquote

from fastapi import (
    APIRouter,
    Form,
    Header,
    HTTPException,
    Path,
    Response,
    status,
)

from beat.auth_tasks import (
    send_confirmation_email_task,
    send_password_reset_email_task,
)
from core import constants
from core.dependency import AuthDependency
from models.users import User
from schemas.core import Message
from schemas.users import (
    OAuthLinkResponse,
    PasswordRequest,
    RecoveryRequest,
    RegisterRequest,
    TokensPair,
    UniversalOAuthRequest,
)
from services.auth import auth_service
from services.base import service
from services.oauth import get_provider_auth_url, process_oauth_login
from services.users import get_user_by_email

auth_router = APIRouter(prefix='/auth')

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка валидации или дублирования данных.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'email',
                            'message': 'Пользователь уже существует.',
                        }
                    ],
                }
            }
        },
    },
    401: {
        'description': 'Ошибка авторизации или истекший токен.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Unauthorized',
                    'details': [
                        {
                            'field': 'Authorization',
                            'message': 'Срок действия токена истек.',
                        }
                    ],
                }
            }
        },
    },
    403: {
        'description': 'Доступ запрещен или аккаунт заблокирован.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Forbidden',
                    'details': [
                        {
                            'field': 'status',
                            'message': 'Аккаунт заблокирован на 1 час.',
                        }
                    ],
                }
            }
        },
    },
}


@auth_router.get(
    '/{provider}/start',
    response_model=OAuthLinkResponse,
    status_code=status.HTTP_200_OK,
    summary='Получить ссылку для редиректа на страницу авторизации сервиса',
)
async def oauth_start(
    provider: str = Path(
        ..., description='Название провайдера (google, gitlab)'
    ),
) -> OAuthLinkResponse:
    auth_url = get_provider_auth_url(provider_name=provider)
    return OAuthLinkResponse(url=auth_url)


@auth_router.post(
    '/{provider}/callback',
    response_model=TokensPair,
    status_code=status.HTTP_200_OK,
    summary='Универсальная авторизация через OAuth2 (google, gitlab)',
)
async def oauth_login(
    auth_data: UniversalOAuthRequest,
    provider: str = Path(
        ..., description='Название провайдера (google, gitlab)'
    ),
) -> TokensPair:
    decoded_code = unquote(auth_data.code)
    result_tokens = await process_oauth_login(
        provider_name=provider, code=decoded_code
    )
    return TokensPair(**result_tokens)


@auth_router.post(
    '/registration',
    response_model=Message,
    summary='Зарегистрировать пользователя',
    responses={400: SWAGGER_RESPONSES},
)
async def register(registration_data: RegisterRequest) -> Message:
    user: User = await get_user_by_email(registration_data.email)
    if user:
        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    'type': 'Ошибка регистрации.',
                    'field': 'email',
                    'msg': constants.USER_ALREADY_EXIST,
                },
            )
    else:
        hashed = await auth_service.crypto.hash_password(
            registration_data.password
        )
        user_data = {
            'email': registration_data.email,
            'password': hashed,
        }
        # TODO: Функция не возвращает объект User - перевести
        # на отдельный сервисный метод без refresh()
        user = await service.add(model=User, values=user_data)

    confirm_token = await auth_service.jwt.create_confirmation_token(user.id)
    send_confirmation_email_task.delay(registration_data.email, confirm_token)

    return {'message': constants.SUCCESS_REGISTRATION}


@auth_router.post(
    '/registration/confirm',
    response_model=Message,
    summary='Подтвердить регистрацию пользователя',
    responses={401: SWAGGER_RESPONSES},
)
async def confirm_registration(
    token: Annotated[str, Header()],
) -> Message:
    payload = await auth_service.jwt.verify_token_payload(token, 'confirm')
    user: User = await service.get(model=User, obj_id=payload['user_id'])

    if not user or user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                'type': 'Ошибка регистрации.',
                'field': 'token',
                'msg': constants.REGISTRATION_ERROR,
            },
        )

    update_data = {'id': payload['user_id'], 'is_active': True}
    await service.update(model=User, values=update_data)

    return {'message': constants.SUCCESS_REGISTRATION_CONFIRM}


@auth_router.post(
    '/login',
    response_model=TokensPair,
    summary='Аутентификация пользователя',
    responses={400: SWAGGER_RESPONSES, 403: SWAGGER_RESPONSES},
)
async def login(
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> TokensPair:
    user = await get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка авторизации.',
                'field': 'email',
                'msg': 'Неверный логин или пароль.',
            },
        )

    # Защита от брутфорса и Argon2 выполняются в рамках одной транзакции
    await auth_service.handle_login_attempt(user, password)

    tokens_data = await auth_service.jwt.create_token_pair(user.id)
    return TokensPair(**tokens_data)


@auth_router.post(
    '/recovery',
    response_model=Message,
    summary='Восстановить пароль',
    responses={400: SWAGGER_RESPONSES},
)
async def recovery_password(recovery_data: RecoveryRequest) -> Message:
    user: User = await get_user_by_email(recovery_data.email)
    if user and user.is_active:
        recovery_token = await auth_service.jwt.create_password_recovery_token(
            user.id
        )
        send_password_reset_email_task.delay(
            recovery_data.email, recovery_token
        )
        return {'message': constants.RECOVERY_EMAIL_SENT}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка доступа.',
                'field': 'email',
                'msg': constants.UNREGISTERED_USER,
            },
        )


@auth_router.post(
    '/recovery/confirm',
    response_model=TokensPair,
    summary='Подтвердить восстановление пароля',
    responses={404: SWAGGER_RESPONSES},
)
async def confirm_recovery_password(
    token: Annotated[str, Header()],
) -> TokensPair:
    payload = await auth_service.jwt.verify_token_payload(
        token, 'password_recovery'
    )
    user: User = await service.get(model=User, obj_id=payload['user_id'])

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка авторизации.',
                'field': 'token',
                'msg': constants.INCORRECT_CREDENTAILS_MESSAGE,
            },
        )

    tokens_data = await auth_service.jwt.create_token_pair(user.id)
    return TokensPair(**tokens_data)


@auth_router.post(
    '/passchange',
    status_code=status.HTTP_200_OK,
    summary='Сменить пароль',
)
async def reset_password(
    password_data: PasswordRequest,
    user: AuthDependency,
) -> Response:
    hashed = await auth_service.crypto.hash_password(password_data.password)
    update_data = {
        'id': user.id,
        'password': hashed,
    }
    await service.update(model=User, values=update_data)
    return Response(status_code=status.HTTP_200_OK)


@auth_router.post(
    '/refresh',
    response_model=TokensPair,
    summary='Обновить токен доступа',
    responses={400: SWAGGER_RESPONSES},
)
async def update_tokens(
    refresh_token: Annotated[str, Header()],
) -> TokensPair:
    if await auth_service.jwt.verify_token_payload(refresh_token, 'refresh'):
        token_object = await auth_service.jwt.get_token_by_refresh(
            refresh_token
        )
        if token_object and token_object.is_active:
            # Атомарная деактивация через изменение флага в памяти сессии
            await auth_service.deactivate_token_object(token_object)
            new_tokens = await auth_service.jwt.create_token_pair(
                token_object.user_id
            )
            return TokensPair(**new_tokens)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            'type': 'Ошибка доступа.',
            'field': 'refresh_token',
            'msg': constants.ACCESS_ERROR,
        },
    )


@auth_router.post(
    '/logout',
    status_code=status.HTTP_200_OK,
    summary='Завершить сессию аутентификации',
)
async def logout(
    user: AuthDependency,
    authorization: str = Header(...),
) -> Response:
    token_str = authorization.replace('Bearer ', '').strip()
    token_obj = await auth_service.jwt.get_token_by_access(token_str)
    if token_obj:
        await auth_service.deactivate_token_object(token_obj)

    return Response(status_code=status.HTTP_200_OK)
