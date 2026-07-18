from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ReminderStatus, SubtaskStatus
from models.taskflow import Reminder, Subtask, TaskList


async def select_next_tasklist_seq_number(
    project_id: int,
    session: AsyncSession,
) -> int:
    """Вычислить следующий порядковый номер для списка задач в проекте."""
    query = select(func.coalesce(func.max(TaskList.seq_number), 0) + 1).where(
        TaskList.project_id == project_id
    )

    result = await session.execute(query)
    return result.scalar_one()


async def bulk_update_subtasks_status_by_tasks(
    task_ids: tuple[int, ...],
    status: SubtaskStatus,
    session: AsyncSession,
) -> None:
    """Пакетно обновить статус подзадач для всех указанных задач."""
    if not task_ids:
        return
    await session.execute(
        update(Subtask)
        .where(Subtask.task_id.in_(task_ids))
        .values(status=status)
    )


async def bulk_delete_queued_reminders_by_tasks(
    task_ids: tuple[int, ...],
    session: AsyncSession,
) -> None:
    """Пакетно удалить запланированные напоминания для указанных задач."""
    if not task_ids:
        return
    await session.execute(
        delete(Reminder).where(
            Reminder.task_id.in_(task_ids),
            Reminder.status == ReminderStatus.QUEUED,
        )
    )
