from typing import Any

from fastapi import APIRouter, Response, status

from core.dependency import (
    ProjectPathDependency,
    TaskListPathDependency,
)
from core.redis import redis_service
from models.taskflow import TaskList
from routers.tasks import task_router
from schemas.tasklist import (
    TaskListCreate,
    TaskListSortRequest,
    TaskListUpdate,
)
from services.base import service
from services.tasklist import (
    create_tasklist_business_logic,
    reorder_tasklist,
    update_tasklist_business_logic,
)

tasklist_router: APIRouter = APIRouter(prefix='/{project_id}/tasklist')

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка валидации бизнес-логики списков задач.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'status',
                            'message': 'Недопустимый статус списка.',
                        }
                    ],
                }
            }
        },
    },
    404: {
        'description': 'Указанный проект или список задач не найден.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'tasklist_id',
                            'message': 'Список задач не найден.',
                        }
                    ],
                }
            }
        },
    },
}


@tasklist_router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    summary='Создать список задач',
    description=(
        'Создает новый список задач внутри проекта. Порядковый '
        'номер seq_number рассчитывается автоматически в СУБД.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def add_tasklist(
    objects: ProjectPathDependency,
    tasklist_data: TaskListCreate,
) -> Response:
    tasklist_dict: dict[str, Any] = tasklist_data.model_dump(
        exclude_unset=True
    )

    await create_tasklist_business_logic(
        project_id=objects.project.id,
        tasklist_dict=tasklist_dict,
    )

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_201_CREATED)


@tasklist_router.patch(
    '/sort/',
    status_code=status.HTTP_200_OK,
    summary='Изменить порядок списка задач',
    description=(
        'Изменяет порядковый индекс seq_number списка задач '
        'перемещением методом Drag-and-Drop.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def sort_tasklists(
    objects: ProjectPathDependency,
    sort_data: TaskListSortRequest,
) -> Response:
    await reorder_tasklist(
        objects.project,
        sort_data.tasklist_id,
        sort_data.new_previous_tasklist_id or 0,
    )

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@tasklist_router.patch(
    '/{tasklist_id}',
    status_code=status.HTTP_200_OK,
    summary='Изменить данные списка задач',
    description=(
        'Обновляет имя или статус списка задач атомарно. Если '
        'статус переведен в DONE, все задачи и подзадачи закрываются.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def update_tasklist(
    objects: TaskListPathDependency,
    tasks_list_data: TaskListUpdate,
) -> Response:
    update_data: dict[str, Any] = tasks_list_data.model_dump(
        exclude_unset=True
    )

    # Вся логика, включая done_all_tasks, теперь внутри одной сессии
    await update_tasklist_business_logic(
        tasklist_id=objects.tasklist.id,
        update_dict=update_data,
    )

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@tasklist_router.delete(
    '/{tasklist_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить список задач',
    description=(
        'Полностью удаляет список задач и все связанные с ним '
        'задачи на уровне каскадов СУБД.'
    ),
    responses={404: SWAGGER_RESPONSES},
)
async def delete_tasklist(
    objects: TaskListPathDependency,
) -> Response:
    await service.delete(TaskList, objects.tasklist.id)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


tasklist_router.include_router(task_router)
