from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from core.dependency import (
    AuthDependency,
    TagPathDependency,
    TaskPathDependency,
)
from core.redis import redis_service
from models.taskflow import Tag
from schemas.tags import TagCreate, TagList, TagUpdate, TaskTags
from services.base import service
from services.tags import search_tags, set_task_tags

tags_router = APIRouter(prefix='/tags')
task_tags_router = APIRouter(prefix='/{task_id}/tags')

SWAGGER_RESPONSES = {
    404: {
        'description': 'Указанный тег или задача не найдены.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'tag_ids',
                            'message': 'Один или несколько тегов не найдены.',
                        }
                    ],
                }
            }
        },
    },
    409: {
        'description': 'Конфликт уникальности названия тега.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Conflict',
                    'details': [
                        {
                            'field': 'name',
                            'message': 'Тег с таким названием уже существует.',
                        }
                    ],
                }
            }
        },
    },
}


@tags_router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    summary='Создать тег',
    responses={**SWAGGER_RESPONSES},
)
async def add_tag(user: AuthDependency, tags_data: TagCreate) -> Response:
    tag_dict: dict[str, Any] = tags_data.model_dump(exclude_unset=True)
    tag_dict['user_id'] = user.id
    try:
        await service.add(Tag, tag_dict)
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'type': 'Ошибка валидации',
                'field': 'name',
                'msg': 'Тег с таким названием уже существует.',
            },
        ) from e

    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_201_CREATED)


@tags_router.patch(
    '/{tag_id}',
    status_code=status.HTTP_200_OK,
    summary='Изменить тег',
    responses={**SWAGGER_RESPONSES},
)
async def update_tag(
    user: AuthDependency,
    tag: TagPathDependency,
    tag_data: TagUpdate,
) -> Response:
    update_data: dict[str, Any] = tag_data.model_dump(exclude_unset=True)
    update_data['id'] = tag.id
    await service.update(Tag, update_data)
    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_200_OK)


@tags_router.get(
    '/',
    response_model=TagList,
    summary='Получить список тегов пользователя',
)
async def get_tags(
    user: AuthDependency,
    q: str = Query(default='', title='Поисковая подстрока'),
) -> TagList:
    return TagList(tags=await search_tags(user_id=user.id, search_param=q))


@task_tags_router.patch(
    '/',
    status_code=status.HTTP_200_OK,
    summary='Изменить список тегов задачи',
    responses={**SWAGGER_RESPONSES},
)
async def update_task_tags(
    user: AuthDependency,
    objects: TaskPathDependency,
    updated_tag_ids: TaskTags,
) -> Response:
    await set_task_tags(
        user_id=user.id,
        task_id=objects.task.id,
        new_tag_ids_model=updated_tag_ids,
    )

    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_200_OK)
