from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.redis import redis_service
from database.db import connection
from db_selectors.projects import select_tasks_for_tasklists
from models.enums import ProjectStatus
from models.taskflow import Project
from models.users import User
from schemas.filters import ProjectFilter, ProjectSort, TaskFilter
from schemas.projects import ProjectDetail, ProjectInfo, ProjectsList


async def get_project_detail(
    project_orm: Project,
    filters: TaskFilter = None,
) -> ProjectDetail:
    return await _build_project_detail_tx(project_orm, filters)


@connection
async def _build_project_detail_tx(
    project_orm: Project,
    filters: TaskFilter,
    session: AsyncSession,
) -> ProjectDetail:
    timezone = project_orm.user.timezone
    project = ProjectDetail.model_validate(project_orm)
    project.user_timezone = timezone

    if project.tasklists:
        list_ids = [tl.id for tl in project.tasklists]
        all_tasks = await select_tasks_for_tasklists(
            list_ids, filters, session
        )

        tasks_by_list = {list_id: [] for list_id in list_ids}
        for task in all_tasks:
            tasks_by_list[task.tasklist_id].append(task)

        for tasklist in project.tasklists:
            from schemas.tasks import TaskInfo

            tasklist.tasks = [
                TaskInfo.model_validate(t) for t in tasks_by_list[tasklist.id]
            ]
            for t in tasklist.tasks:
                t.user_timezone = timezone

    return project


@connection
async def get_projects(
    user: User,
    filters: ProjectFilter,
    session: AsyncSession,
) -> ProjectsList:
    cache_key = (
        f'user:{user.id}:projects:q={filters.q}:'
        f'sort={filters.order_by}:status={filters.status}'
    )

    cached_data = await redis_service.get(cache_key)
    if cached_data:
        return ProjectsList.model_validate_json(cached_data)

    statuses = (
        [ProjectStatus.IN_PROGRESS, ProjectStatus.ON_PAUSE, ProjectStatus.DONE]
        if not filters.status
        else filters.status
    )

    sort_params = [
        case(
            (Project.status == ProjectStatus.IN_PROGRESS, 0),
            (Project.status == ProjectStatus.ON_PAUSE, 1),
            (Project.status == ProjectStatus.DONE, 2),
        ),
    ]
    match filters.order_by:
        case None | ProjectSort.CREATED_DESC:
            sort_params = [Project.created_at.desc(), Project.id.desc()]
        case ProjectSort.CREATED_ASC:
            sort_params = [Project.created_at, Project.id]
        case ProjectSort.NAME_ASC:
            sort_params = [Project.name]
        case ProjectSort.NAME_DESC:
            sort_params = [Project.name.desc()]
        case ProjectSort.URGENT:
            sort_params.append(Project.deadline)
        case ProjectSort.NON_URGENT:  # pragma: no branch
            sort_params.append(Project.deadline.desc())

    query = (
        select(Project)
        .where(Project.user_id == user.id)
        .filter(
            Project.name.icontains(filters.q),
            Project.status.in_(statuses),
        )
        .order_by(*sort_params)
    )
    result = await session.execute(query)

    projects = [ProjectInfo.model_validate(p) for p in result.scalars().all()]
    for p in projects:
        p.user_timezone = user.timezone

    response_data = ProjectsList(projects=projects)
    await redis_service.set(
        cache_key, response_data.model_dump_json(), ttl=300
    )
    return response_data
