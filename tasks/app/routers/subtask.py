from fastapi import APIRouter, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.dependency import SubtaskPathDependency, TaskPathDependency
from core.redis import redis_service
from models.taskflow import Subtask
from schemas.subtasks import SubtaskCreate, SubtaskUpdate
from services.base import service

subtask_router = APIRouter(prefix='/{task_id}/subtask')

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка бизнес-валидации подзадачи.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'status',
                            'message': 'Нельзя изменять готовую подзадачу.',
                        }
                    ],
                }
            }
        },
    },
    404: {
        'description': 'Родительская задача или подзадача не найдена.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'subtask_id',
                            'message': 'Подзадача не найдена в проекте.',
                        }
                    ],
                }
            }
        },
    },
}


@subtask_router.post(
    '/',
    status_code=status.HTTP_201_CREATED,
    summary='Создать подзадачу',
    responses={**SWAGGER_RESPONSES},
)
async def create_subtask(
    objects: TaskPathDependency,
    subtask_model: SubtaskCreate,
) -> Response:
    subtask_dict = subtask_model.model_dump()
    subtask_dict['task_id'] = objects.task.id
    await service.add(Subtask, subtask_dict)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_201_CREATED)


@subtask_router.patch(
    '/{subtask_id}',
    status_code=status.HTTP_200_OK,
    summary='Обновить подзадачу',
    responses={**SWAGGER_RESPONSES},
)
async def update_subtask(
    objects: SubtaskPathDependency,
    subtask_update: SubtaskUpdate,
) -> Response:
    try:
        subtask_update.subtask = objects.subtask
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    update_data = subtask_update.model_dump(exclude_unset=True)
    update_data['id'] = objects.subtask.id
    await service.update(model=Subtask, values=update_data)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_200_OK)


@subtask_router.delete(
    '/{subtask_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить подзадачу',
    responses={404: SWAGGER_RESPONSES},
)
async def delete_subtask(objects: SubtaskPathDependency) -> Response:
    await service.delete(Subtask, objects.subtask.id)

    await redis_service.invalidate(
        f'user:{objects.project.user_id}:projects:*'
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
