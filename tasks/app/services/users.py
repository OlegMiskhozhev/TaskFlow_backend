import json
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.minio import MinioHandler
from database.db import connection
from models.enums import ProjectStatus
from models.users import Avatar, Token, User
from schemas.users import UserDetail, UserProject

# Клиент для бакета аватарок
client = MinioHandler(
    settings.minio_settings.MINIO_URL,
    settings.minio_settings.MINIO_ROOT_USER,
    settings.minio_settings.MINIO_ROOT_PASSWORD,
    'avatars',
)

# Синхронный кэш-клиент Redis
redis_cache = aioredis.from_url(
    settings.redis_settings.redis_url, decode_responses=True
)


@connection
async def get_user_by_email(email: str, session: AsyncSession) -> User | None:
    """Получить пользователя по email в нижнем регистре."""
    query = select(User).where(func.lower(User.email) == func.lower(email))
    user = await session.execute(query)
    return user.scalar_one_or_none()


@connection
async def get_user_by_token(token: str, session: AsyncSession) -> User | None:
    """Получить пользователя по токену доступа сессии."""
    query = (
        select(Token)
        .where(Token.access_token == token)
        .order_by(Token.id.desc())
    )
    result = await session.execute(query)
    token_record = result.scalars().first()

    if token_record and token_record.is_active:
        return token_record.user
    return None


async def get_user_detail(user_orm: User) -> UserDetail:
    """Сформировать схему профиля пользователя без лишних SQL-запросов."""
    user = UserDetail.model_validate(user_orm)

    # Высокопроизводительное вычисление ссылки из связи в ОЗУ (Уничтожен N+1!)
    if user_orm.avatar:
        user.avatar_url = await client.get_url(
            f'{user_orm.avatar.minio_name}.{user_orm.avatar.mime_type}'
        )
    else:
        user.avatar_url = None

    user.projects = [
        UserProject.model_validate(project)
        for project in user_orm.projects
        if project.status != ProjectStatus.ARCHIVE
    ]
    return user


async def get_cached_user_detail(user_orm: User) -> dict[str, Any]:
    """Получить профиль пользователя с поддержкой кэширования в Redis."""
    cache_key = f'user:{user_orm.id}:profile'
    cached_data = await redis_cache.get(cache_key)

    if cached_data:
        return json.loads(cached_data)

    user_detail = await get_user_detail(user_orm)
    dumped_data = user_detail.model_dump()

    # Кэшируем профиль ровно на 1 час
    await redis_cache.set(cache_key, json.dumps(dumped_data), ex=3600)
    return dumped_data


@connection
async def update_avatar(
    user: User, file: UploadFile, session: AsyncSession
) -> None:
    """Обновляет аватар пользователя (Валидация пройдена в зависимости)."""
    extension = file.filename.rsplit('.', 1)[-1].lower()
    minio_name = str(uuid4())
    object_name = f'{minio_name}.{extension}'

    # Загружаем бинарник в бакет 'avatars'
    await client.upload_file(object_name, file.file, file.size)

    query = select(Avatar).where(Avatar.user_id == user.id)
    result = await session.execute(query)
    avatar = result.scalar_one_or_none()

    old_file_to_delete = None
    if avatar:
        # Запоминаем старый файл для удаления после успешного коммита
        old_file_to_delete = f'{avatar.minio_name}.{avatar.mime_type}'
        avatar.filename = file.filename
        avatar.minio_name = minio_name
        avatar.mime_type = extension
    else:
        avatar = Avatar(
            filename=file.filename,
            minio_name=minio_name,
            mime_type=extension,
            user_id=user.id,
        )
        session.add(avatar)

    await session.commit()

    # Чистим S3 строго после успешной фиксации данных в PostgreSQL
    if old_file_to_delete:
        try:
            await client.remove_file(old_file_to_delete)
        except Exception:
            pass
