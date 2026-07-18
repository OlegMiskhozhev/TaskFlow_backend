from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import TaskPriority, TaskStatus
from models.taskflow import Tag, Task
from schemas.filters import TaskFilter


async def select_tasks_for_tasklists(
    list_ids: list[int],
    filters: TaskFilter,
    session: AsyncSession,
) -> list[Task]:
    if not list_ids:
        return []

    query_filters = []
    if filters and filters.q:
        query_filters.append(
            or_(
                Task.name.icontains(filters.q),
                Task.description.icontains(filters.q),
            )
        )
    if filters and filters.tag:
        query_filters.append(Task.tags.any(Tag.name.in_(filters.tag)))
    if filters and filters.priority:
        query_filters.append(Task.priority.in_(filters.priority))
    if filters and filters.deadline_from:
        query_filters.append(Task.deadline >= filters.deadline_from)
    if filters and filters.deadline_to:
        query_filters.append(Task.deadline <= filters.deadline_to)

    query = (
        select(Task)
        .where(Task.tasklist_id.in_(list_ids))
        .filter(*query_filters)
        .order_by(
            case(
                (Task.status == TaskStatus.IN_PROGRESS, 0),
                (Task.status == TaskStatus.SCHEDULE, 1),
                (Task.status == TaskStatus.DONE, 2),
            ),
            case(
                (
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.priority == TaskPriority.HIGH,
                    ),
                    0,
                ),
                (
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.priority == TaskPriority.MID,
                        Task.deadline < func.now(),
                    ),
                    1,
                ),
                (
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.priority == TaskPriority.LOW,
                        Task.deadline < func.now(),
                    ),
                    2,
                ),
                (
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.priority == TaskPriority.MID,
                    ),
                    3,
                ),
                (
                    and_(
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.priority == TaskPriority.LOW,
                    ),
                    4,
                ),
            ),
            case(
                (Task.priority == TaskPriority.HIGH, 0),
                (Task.priority == TaskPriority.MID, 1),
                (Task.priority == TaskPriority.LOW, 2),
            ),
            Task.deadline,
        )
    )
    result = await session.execute(query)
    return result.scalars().all()
