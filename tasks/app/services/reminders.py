from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import connection
from db_selectors.reminders import select_user_sent_reminders
from models.enums import (
    ReminderChannel,
    ReminderPeriodic,
    ReminderStatus,
)
from models.taskflow import Reminder, Task
from models.users import User
from schemas.reminders import CreateReminder, ReminderInfo, UserReminders


async def make_reminders_datetimes(
    task_dict: dict[str, Any],
) -> list[datetime]:
    """Создать список дат напоминаний в соответствии с периодичностью."""
    dates = []
    reminder_periodic = task_dict.get('reminder_periodic')
    start = task_dict.get('reminder_datetime')
    deadline = task_dict.get('deadline')

    if not start:
        return dates

    current = start
    match reminder_periodic:
        case ReminderPeriodic.NONE:
            dates.append(current)
            return dates

        case ReminderPeriodic.DAILY:
            while current <= deadline:
                dates.append(current)
                current += timedelta(days=1)

        case ReminderPeriodic.WEEKLY:
            while current <= deadline:
                dates.append(current)
                current += timedelta(weeks=1)

        case ReminderPeriodic.MONTHLY:
            while current <= deadline:
                dates.append(current)
                target_day = current.day
                if current.month == 12:
                    new_year = current.year + 1
                    new_month = 1
                else:
                    new_year = current.year
                    new_month = current.month + 1

                last_day = monthrange(new_year, new_month)[1]
                new_day = min(target_day, last_day)
                current = current.replace(
                    year=new_year,
                    month=new_month,
                    day=new_day,
                )

        case ReminderPeriodic.WEEKDAYS:
            while current <= deadline:
                if current.weekday() < 5:
                    dates.append(current)
                current += timedelta(days=1)
    return dates


async def _delete_reminder_objects(
    task_id: int,
    session: AsyncSession,
) -> None:
    """Внутренний атомарный шаг удаления без открытия новых сессий."""
    await session.execute(
        delete(Reminder).where(
            Reminder.task_id == task_id,
            Reminder.status == ReminderStatus.QUEUED,
        )
    )
    await session.flush()


@connection
async def delete_reminder_objects(
    task_id: int,
    session: AsyncSession,
) -> None:
    """Публичный метод удаления для одиночных вызовов из ручек задач."""
    await _delete_reminder_objects(task_id, session)
    await session.commit()


@connection
async def update_task_reminders(
    reminder_model: CreateReminder,
    session: AsyncSession,
) -> None:
    """Изменить настройки и обновить объекты напоминаний за 1 транзакцию."""
    task_id = reminder_model.task.id
    task_dict = reminder_model.model_dump()
    task_dict['deadline'] = reminder_model.task.deadline

    # Удаляем старые запланированные напоминания внутри текущей сессии
    await _delete_reminder_objects(task_id, session)

    stmt = update(Task).where(Task.id == task_id).values(**task_dict)
    await session.execute(stmt)

    dates = await make_reminders_datetimes(task_dict)
    if dates:
        values_list = [
            {
                'send_time': dt,
                'channel': ReminderChannel.EMAIL,
                'status': ReminderStatus.QUEUED,
                'task_id': task_id,
                'was_read': False,
            }
            for dt in dates
        ]
        await session.execute(insert(Reminder).values(values_list))

    await session.commit()


@connection
async def get_user_reminders(
    user: User,
    session: AsyncSession,
) -> UserReminders:
    """Получить отправленные напоминания пользователя через 1 чистый SQL."""
    reminder_orms = await select_user_sent_reminders(user.id, session)

    reminders = [ReminderInfo.model_validate(r) for r in reminder_orms]
    for r in reminders:
        r.user_timezone = user.timezone.value

    return UserReminders(reminders=reminders)
