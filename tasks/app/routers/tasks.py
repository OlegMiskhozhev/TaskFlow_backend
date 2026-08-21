from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.dependency import TaskListPathDependency, TaskPathDependency
from core.redis import redis_service
from models.taskflow import Task
from routers.attachments import task_attachments_router
from routers.reminders import reminders_router
from routers.subtask import subtask_router
from routers.tags import task_tags_router
from schemas.tasks import (
    ReminderPeriodic,
    TaskCreate,
    TaskDetail,
    TaskInfoUpdate,
    TaskMove,
    TaskPeriodUpdate,
    TaskStatusUpdate,
)
from services.base import service
from services.reminders import delete_reminder_objects
from services.tasks import (
    get_task_detail,
    move_task_business_logic,
    update_task_status_business_logic,
)

task_router = APIRouter(prefix='/{tasklist_id}/task')

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка валидации бизнес-логики задачи.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'status',
                            'message': 'Нельзя редактировать готовую задачу.',
                        }
                    ],
                }
            }
        },
    },
    404: {
        'description': 'Указанный список или задача не найдены.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'task_id',
                            'message': 'Задача не найдена в текущем проекте.',
                        }
                    ],
                }
            }
        },
    },
}


@task_router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    summary='Создать задачу',
    description=(
        'Создает новую базовую карточку задачи. По умолчанию '
        'выставляются приоритет LOW и статус IN_PROGRESS. Все остальные '
        'параметры настраиваются через PATCH-ручки.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def create_task(
    objects: TaskListPathDependency,
    task_model: TaskCreate,
) -> Response:
    task_model.user_timezone = objects.project.user.timezone

    task_dict: dict[str, Any] = task_model.model_dump()
    task_dict['tasklist_id'] = objects.tasklist.id
    await service.add(Task, values=task_dict)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_201_CREATED)


@task_router.get(
    '/{task_id}',
    response_model=TaskDetail,
    summary='Детали задачи',
    description=(
        'Возвращает полную информацию о задаче, включая списки тегов, '
        'подзадач и сгенерированные временные ссылки на вложения MinIO.'
    ),
    responses={404: SWAGGER_RESPONSES[404]},
)
async def get_task(objects: TaskPathDependency) -> TaskDetail:
    return await get_task_detail(objects.task)


@task_router.patch(
    '/{task_id}',
    response_model=TaskDetail,
    summary='Обновить информацию о задаче',
    description=(
        'Обновляет текстовые поля (название, описание) и приоритет задачи. '
        'Блокирует изменения, если задача уже переведена в статус DONE.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def update_task(
    objects: TaskPathDependency,
    task_update: TaskInfoUpdate,
) -> TaskDetail:
    try:
        task_update.task = objects.task
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    update_data: dict[str, Any] = task_update.model_dump(exclude_unset=True)
    update_data['id'] = objects.task.id
    updated_task: Task = await service.update(Task, update_data)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return await get_task_detail(updated_task)


@task_router.patch(
    '/{task_id}/period',
    status_code=status.HTTP_200_OK,
    summary='Изменить сроки начала и завершения задачи',
    description=(
        'Изменяет дедлайн и дату старта задачи на основе трех '
        'полей (дата, часы, минуты). При переносе сроков настройки '
        'пользовательских напоминаний сбрасываются в NONE.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def update_task_period(
    objects: TaskPathDependency,
    task_period: TaskPeriodUpdate,
) -> Response:
    try:
        task_period.user_timezone = objects.project.user.timezone
        task_period.task = objects.task
        task_period.project = objects.project
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    valid_data: dict[str, Any] = task_period.model_dump(exclude_unset=True)
    valid_data['id'] = objects.task.id
    valid_data['reminder_datetime'] = None
    valid_data['reminder_periodic'] = ReminderPeriodic.NONE

    await service.update(Task, valid_data)
    await delete_reminder_objects(objects.task.id)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@task_router.patch(
    '/{task_id}/status',
    status_code=status.HTTP_200_OK,
    summary='Изменить статус задачи',
    description=(
        'Обновляет текущий статус задачи. При переводе задачи '
        'в DONE запускается атомарный каскад: пакетно закрываются '
        'все подзадачи и удаляются активные напоминания из очереди.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def update_task_status(
    objects: TaskPathDependency,
    task_status: TaskStatusUpdate,
) -> Response:
    try:
        task_status.task = objects.task
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    status_dict: dict[str, Any] = task_status.model_dump(exclude_unset=True)

    await update_task_status_business_logic(
        task_id=objects.task.id,
        status_dict=status_dict,
    )

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@task_router.patch(
    '/{task_id}/move',
    status_code=status.HTTP_200_OK,
    summary='Переместить задачу в другой список',
    description=(
        'Переносит задачу между списками (канбан-колонками). '
        'Операция жестко блокируется, если целевой список задач '
        'принадлежит чужому или удаленному проекту.'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def move_task(
    objects: TaskPathDependency,
    move_data: TaskMove,
) -> Response:
    await move_task_business_logic(
        task_id=objects.task.id,
        new_tasklist_id=move_data.tasklist_id,
        current_project_id=objects.project.id,
    )

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@task_router.delete(
    '/{task_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить задачу',
    description=(
        'Полностью удаляет задачу из системы. Связанные вложения, '
        'подзадачи и теги очищаются на уровне каскадов СУБД.'
    ),
    responses={404: SWAGGER_RESPONSES},
)
async def delete_task(objects: TaskPathDependency) -> Response:
    await service.delete(model=Task, obj_id=objects.task.id)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


task_router.include_router(subtask_router)
task_router.include_router(task_tags_router)
task_router.include_router(task_attachments_router)
task_router.include_router(reminders_router)
