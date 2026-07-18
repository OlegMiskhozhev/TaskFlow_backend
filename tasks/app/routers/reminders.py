from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.dependency import (
    AuthDependency,
    ReminderPathDependency,
    TaskPathDependency,
)
from models.taskflow import Reminder
from schemas.reminders import CreateReminder, ReminderUpdate, UserReminders
from services.base import service
from services.reminders import get_user_reminders, update_task_reminders

reminders_router = APIRouter(prefix='/{task_id}/reminders')
user_reminders_router = APIRouter(prefix='/reminders')

SWAGGER_RESPONSES = {
    400: {
        'description': 'Ошибка бизнес-валидации параметров напоминания.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Bad Request',
                    'details': [
                        {
                            'field': 'reminder_periodic',
                            'message': 'Требуется дедлайн для повторов.',
                        }
                    ],
                }
            }
        },
    },
    404: {
        'description': 'Указанная задача или напоминание не найдены.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'reminder_id',
                            'message': 'Напоминание не существует.',
                        }
                    ],
                }
            }
        },
    },
}


@reminders_router.patch(
    '/',
    summary='Создать или изменить напоминание',
    description=(
        'Устанавливает точное время напоминания для задачи. Если выбрана '
        'периодичность (DAILY, WEEKLY и др.), одной транзакцией генерируется '
        'цепочка напоминаний вплоть до даты дедлайна задачи. Старые записи '
        'в статусе QUEUED автоматически вычищаются.'
    ),
    status_code=status.HTTP_201_CREATED,
    responses={**SWAGGER_RESPONSES},
)
async def reminder_create(
    objects: TaskPathDependency,
    reminder_model: CreateReminder,
) -> Response:
    try:
        reminder_model.user_timezone = objects.project.user.timezone.value
        reminder_model.task = objects.task
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e

    await update_task_reminders(reminder_model)
    return Response(status_code=status.HTTP_201_CREATED)


@user_reminders_router.get(
    '/',
    response_model=UserReminders,
    summary='Получить все напоминания пользователя',
    description=(
        'Возвращает глобальный структурированный список всех отправленных '
        'пользователю напоминаний (ленту уведомлений) с сортировкой '
        'от самых свежих к более старым.'
    ),
    responses={404: SWAGGER_RESPONSES},
)
async def get_reminders(current_user: AuthDependency) -> UserReminders:
    return await get_user_reminders(current_user)


@user_reminders_router.patch(
    '/{reminder_id}',
    summary='Прочитать напоминание',
    description=(
        'Помечает выбранное отправленное напоминание в ленте пользователя '
        'как прочитанное (выставляет флаг was_read=True).'
    ),
    responses={**SWAGGER_RESPONSES},
)
async def read_reminders(
    reminder: ReminderPathDependency,
    reminder_read: ReminderUpdate,
) -> Response:
    update_data: dict[str, Any] = reminder_read.model_dump(exclude_unset=True)
    update_data['id'] = reminder.id
    await service.update(Reminder, update_data)
    return Response(status_code=status.HTTP_200_OK)


@user_reminders_router.delete(
    '/{reminder_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить напоминание',
    description=(
        'Полностью удаляет выбранное напоминание из истории и ленты '
        'уведомлений текущего пользователя.'
    ),
    responses={404: SWAGGER_RESPONSES},
)
async def delete_reminders(
    reminder: ReminderPathDependency,
) -> Response:
    await service.delete(Reminder, reminder.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
