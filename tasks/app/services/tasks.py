from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import connection
from db_selectors.tasklist import (
    bulk_delete_queued_reminders_by_tasks,
    bulk_update_subtasks_status_by_tasks,
)
from models.enums import SubtaskStatus, TaskStatus
from models.taskflow import Task, TaskList
from schemas.tasks import TaskDetail
from services.attachments import client


async def get_task_detail(task_orm: Task) -> TaskDetail | None:
    """Получить объект задачи с генерацией ссылок на вложения MinIO."""
    task = TaskDetail.model_validate(task_orm)
    task.user_timezone = task_orm.tasklist.project.user.timezone

    for attachment_schema, attachment_orm in zip(
        task.attachments, task_orm.attachments, strict=True
    ):
        obj_name = (
            f'{attachment_orm.minio_name}.{attachment_orm.mime_type.value}'
        )
        attachment_schema.url = await client.get_url(obj_name)

    return task


@connection
async def update_task_status_business_logic(
    task_id: int,
    status_dict: dict[str, Any],
    session: AsyncSession,
) -> None:
    """Изменить статус задачи и каскадно закрыть вложенности атомарно."""
    task = await session.get(Task, task_id)
    if not task:
        return

    new_status = status_dict.get('status')
    task.status = new_status

    if new_status == TaskStatus.DONE:
        task_id_tuple = (task_id,)
        await bulk_update_subtasks_status_by_tasks(
            task_id_tuple, SubtaskStatus.DONE, session
        )
        await bulk_delete_queued_reminders_by_tasks(task_id_tuple, session)

    await session.commit()


@connection
async def move_task_business_logic(
    task_id: int,
    new_tasklist_id: int,
    current_project_id: int,
    session: AsyncSession,
) -> None:
    """Переместить задачу в другой список в рамках одного проекта."""
    new_tasklist = await session.get(TaskList, new_tasklist_id)

    if not new_tasklist or new_tasklist.project_id != current_project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка валидации',
                'field': 'tasklist_id',
                'msg': (
                    'Список задач для перемещения не найден или '
                    'находится в другом проекте.'
                ),
            },
        )

    task = await session.get(Task, task_id)
    if task:
        task.tasklist_id = new_tasklist_id

    await session.commit()
