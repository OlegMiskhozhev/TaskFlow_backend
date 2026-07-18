from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import connection
from db_selectors.tasklist import (
    bulk_delete_queued_reminders_by_tasks,
    bulk_update_subtasks_status_by_tasks,
    select_next_tasklist_seq_number,
)
from models.enums import (
    SubtaskStatus,
    TaskListStatus,
    TaskStatus,
)
from models.taskflow import Project, Task, TaskList


@connection
async def create_tasklist_business_logic(
    project_id: int,
    tasklist_dict: dict[str, Any],
    session: AsyncSession,
) -> TaskList:
    """Создать список задач с безопасным автоинкрементом seq_number."""
    next_seq = await select_next_tasklist_seq_number(project_id, session)

    tasklist_dict['project_id'] = project_id
    tasklist_dict['seq_number'] = next_seq

    new_item = TaskList(**tasklist_dict)
    session.add(new_item)

    await session.commit()


@connection
async def update_tasklist_business_logic(
    tasklist_id: int,
    update_dict: dict[str, Any],
    session: AsyncSession,
) -> TaskList | None:
    """Обновить список задач и все вложенные элементы за 1 транзакцию."""
    tasklist = await session.get(TaskList, tasklist_id)
    if not tasklist:
        return None

    # 1. Сначала применяем текстовые или статусные изменения к самому списку
    for field, value in update_dict.items():
        setattr(tasklist, field, value)

    # 2. Если список переводится в DONE — каскадно закрываем всё внутри
    if update_dict.get('status') == TaskListStatus.DONE:
        # Переводим все задачи этого списка в статус DONE
        await session.execute(
            update(Task)
            .where(Task.tasklist_id == tasklist_id)
            .values(status=TaskStatus.DONE)
        )

        # Выгружаем ID всех задач этого списка в экономичный кортеж
        tasks_ids = await session.execute(
            select(Task.id).where(Task.tasklist_id == tasklist_id)
        )
        task_id_tuple = tuple(tasks_ids.scalars().all())

        if task_id_tuple:
            # Пакетно закрываем подзадачи за 1 SQL-запрос
            await bulk_update_subtasks_status_by_tasks(
                task_id_tuple, SubtaskStatus.DONE, session
            )
            # Пакетно удаляем напоминания за 1 SQL-запрос
            await bulk_delete_queued_reminders_by_tasks(task_id_tuple, session)

    # 3. Фиксируем все изменения пачкой на диск
    await session.commit()


@connection
async def reorder_tasklist(
    project: Project,
    tasklist_id: int,
    previous_tasklist_id: int | None,
    session: AsyncSession,
) -> None:
    """Изменить порядок списка задач среди активных списков проекта."""
    project = await session.merge(project)
    all_tasklists = tuple(project.tasklists)

    current_tasklist = next(
        (item for item in all_tasklists if item.id == tasklist_id), None
    )

    if not current_tasklist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'tad_ids',
                'msg': 'Перемещаемый список задач не найден.',
            },
        )

    if current_tasklist.status != TaskListStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка доступа',
                'field': '',
                'msg': (
                    'Ручная сортировка доступна только для активных '
                    'списков задач.'
                ),
            },
        )

    active_tasklists = [
        item for item in all_tasklists if item.status == TaskListStatus.ACTIVE
    ]

    current_index = next(
        (
            index
            for index, item in enumerate(active_tasklists)
            if item.id == tasklist_id
        ),
        None,
    )

    current_item = active_tasklists.pop(current_index)

    if not previous_tasklist_id:
        active_tasklists.insert(0, current_item)
    else:
        after_item = next(
            (
                item
                for item in active_tasklists
                if item.id == previous_tasklist_id
            ),
            None,
        )
        if not after_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    'type': 'Ошибка доступа',
                    'field': 'tad_ids',
                    'msg': (
                        'Список задач, после которого нужно вставить '
                        'текущий, не найден.'
                    ),
                },
            )

        insert_index = (
            next(
                index
                for index, item in enumerate(active_tasklists)
                if item.id == previous_tasklist_id
            )
            + 1
        )
        active_tasklists.insert(insert_index, current_item)

    inactive_task_lists = [
        item for item in all_tasklists if item.status != TaskListStatus.ACTIVE
    ]

    final_tasklists = tuple(active_tasklists + inactive_task_lists)

    for temp_seq, task_list in enumerate(final_tasklists, start=1):
        task_list.seq_number = -temp_seq

    await session.flush()

    for seq_number, task_list in enumerate(final_tasklists, start=1):
        task_list.seq_number = seq_number

    await session.commit()
