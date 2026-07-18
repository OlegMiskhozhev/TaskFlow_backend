from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.dependency import AuthDependency, ProjectPathDependency
from core.redis import redis_service
from models.taskflow import Project
from routers.attachments import attachments_router
from routers.tags import tags_router
from routers.tasklist import tasklist_router
from schemas.filters import ProjectFilter, TaskFilter
from schemas.projects import (
    ProjectCreate,
    ProjectDetail,
    ProjectsList,
    ProjectUpdate,
)
from services.base import service
from services.projects import get_project_detail, get_projects
from services.users import redis_cache

project_router = APIRouter(prefix='/projects', tags=['Проекты'])
project_router.include_router(tags_router)
project_router.include_router(attachments_router)

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка нарушения бизнес-логики или сроков задач.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'deadline',
                            'message': 'Сроки задач превышают лимит.',
                        }
                    ],
                }
            }
        },
    },
    422: {
        'description': 'Ошибка валидации входящих параметров.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Validation Error',
                    'details': [
                        {
                            'field': 'deadline',
                            'message': 'Дедлайн не может быть в прошлом.',
                        }
                    ],
                }
            }
        },
    },
}


@project_router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDetail,
    summary='Создать проект',
    description=(
        'Создает личный проект. Срок завершения проекта '
        'автоматически преобразуется в формат UTC.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def create_project(
    user: AuthDependency, project_data: ProjectCreate
) -> ProjectDetail:
    try:
        project_data.user_timezone = user.timezone
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    new_project: dict[str, Any] = project_data.model_dump()
    new_project['user_id'] = user.id
    project: Project = await service.add(Project, new_project)

    await redis_service.invalidate(f'user:{user.id}:projects:*')
    await redis_cache.delete(f'user:{user.id}:profile')
    return await get_project_detail(project)


@project_router.get(
    '/',
    response_model=ProjectsList,
    summary='Получить список проектов',
    description=(
        'Возвращает список проектов пользователя '
        'с кэшированием в Redis на 5 минут.'
    ),
)
async def get_projects_list(
    user: AuthDependency,
    project_filters: ProjectFilter = Query(title='Фильтры и сортировка'),
) -> ProjectsList:
    return await get_projects(user, project_filters)


@project_router.get(
    '/{project_id}',
    response_model=ProjectDetail,
    summary='Детали проекта',
    description=(
        'Возвращает полную структуру проекта '
        'с вложенными списками задач через 1 SQL-запрос.'
    ),
)
async def get_project(
    objects: ProjectPathDependency,
    task_filters: TaskFilter = Query(title='Фильтры и сортировка'),
) -> ProjectDetail:
    return await get_project_detail(objects.project, task_filters)


# TODO: Ввести оганичение на запрет редактирования архивного проекта
@project_router.patch(
    '/{project_id}',
    response_model=ProjectDetail,
    summary='Обновить проект',
    description=(
        'Частично обновляет поля проекта, валидирует сроки '
        'дочерних задач или переводит проект в архив.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def update_project(
    objects: ProjectPathDependency,
    update_data: ProjectUpdate,
    task_filters: TaskFilter = Query(title='Фильтры и сортировка'),
) -> ProjectDetail:
    try:
        update_data.user_timezone = objects.project.user.timezone
        update_data.project = objects.project
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    valid_update_data: dict[str, Any] = update_data.model_dump(
        exclude_unset=True
    )
    valid_update_data['id'] = objects.project.id
    updated_project: Project = await service.update(Project, valid_update_data)

    user_id = objects.project.user_id
    await redis_service.invalidate(f'user:{user_id}:projects:*')
    await redis_cache.delete(f'user:{user_id}:profile')
    return await get_project_detail(updated_project, task_filters)


project_router.include_router(tasklist_router)
