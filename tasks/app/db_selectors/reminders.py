from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import ReminderStatus
from models.taskflow import Project, Reminder, Task, TaskList


async def select_user_sent_reminders(
    user_id: int,
    session: AsyncSession,
) -> tuple[Reminder, ...]:
    """Пакетно извлечь все отправленные напоминания пользователя."""
    query = (
        select(Reminder)
        .join(Task, Reminder.task_id == Task.id)
        .join(TaskList, Task.tasklist_id == TaskList.id)
        .join(Project, TaskList.project_id == Project.id)
        .where(
            Project.user_id == user_id,
            Reminder.status == ReminderStatus.SENT,
        )
        .order_by(Reminder.send_time.desc())
    )
    result = await session.execute(query)
    return tuple(result.scalars().all())
