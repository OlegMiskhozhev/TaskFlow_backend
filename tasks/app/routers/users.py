from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError

from core.dependency import AuthDependency, avatar_file_dependency
from core.redis import redis_service
from models.users import User
from routers.auth import auth_router
from routers.reminders import user_reminders_router
from schemas.users import Avatar, UserDetail, UserId, UserUpdate
from services.base import service
from services.users import (
    get_cached_user_detail,
    redis_cache,
    update_avatar,
)

user_router = APIRouter(prefix='/user', tags=['Пользователь'])

SWAGGER_RESPONSES = {
    409: {
        'description': 'Конфликт уникальности имени пользователя.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Conflict',
                    'details': [
                        {
                            'field': 'username',
                            'message': 'Имя пользователя уже занято.',
                        }
                    ],
                }
            }
        },
    }
}


@user_router.get(
    '/avatar',
    response_model=Avatar,
    summary='Получить ссылку на файл аватара пользователя',
)
async def avatar_info(user: AuthDependency) -> Avatar:
    # Оптимизировано: берем из кэша профиля, экономя походы в БД и S3
    profile = await get_cached_user_detail(user)
    return {'avatar_url': profile.get('avatar_url')}


@user_router.post(
    '/avatar',
    status_code=status.HTTP_201_CREATED,
    summary='Установить аватар пользователя',
)
async def set_avatar(
    user: AuthDependency,
    file: UploadFile = Depends(avatar_file_dependency),
) -> Response:
    await update_avatar(user, file)

    # Атомарно инвалидируем кэш профиля при смене аватара
    await redis_cache.delete(f'user:{user.id}:profile')
    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_201_CREATED)


@user_router.get(
    '/me',
    response_model=UserDetail,
    summary='Получить профиль пользователя',
)
async def get_user_profile(user: AuthDependency) -> dict[str, Any]:
    return await get_cached_user_detail(user)


@user_router.patch(
    '/me',
    response_model=UserDetail,
    summary='Обновить профиль пользователя',
    responses={409: SWAGGER_RESPONSES},
)
async def update_user_profile(
    user_data: UserUpdate,
    current_user: AuthDependency,
) -> dict[str, Any]:
    update_data: dict[str, Any] = user_data.model_dump(exclude_unset=True)
    update_data['id'] = current_user.id

    try:
        updated_user: User = await service.update(
            model=User, values=update_data
        )
    except IntegrityError as e:
        # Исправлен баг 500 от тестировщика: перехватываем конфликт СУБД
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'type': 'Ошибка валидации',
                'field': 'username',
                'msg': (
                    'Имя пользователя уже занято, '
                    'попробуйте использовать другое.'
                ),
            },
        ) from e

    # Инвалидируем кэш профиля и экранов при изменении личных данных
    await redis_cache.delete(f'user:{current_user.id}:profile')
    await redis_service.invalidate(f'user:{current_user.id}:projects:*')
    return await get_cached_user_detail(updated_user)


@user_router.get(
    '/id',
    response_model=UserId,
    summary='Получить id пользователя',
)
async def get_user_id(user: AuthDependency) -> UserId:
    return UserId(id=user.id)


user_router.include_router(auth_router)
user_router.include_router(user_reminders_router)
