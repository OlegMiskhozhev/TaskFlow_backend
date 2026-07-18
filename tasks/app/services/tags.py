from fastapi import HTTPException, status
from sqlalchemy import and_, delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core import constants
from database.db import connection
from models.taskflow import Tag, task_tag
from schemas.tags import TaskTags


@connection
async def set_task_tags(
    user_id: int,
    task_id: int,
    new_tag_ids_model: TaskTags,
    session: AsyncSession,
) -> None:
    """Синхронизировать теги задачи в рамках одной чистой транзакции."""
    current_result = await session.execute(
        select(task_tag.c.tag_id).where(task_tag.c.task_id == task_id)
    )
    current_set = set(current_result.scalars().all())
    new_set = set(new_tag_ids_model.tag_ids)

    tags_to_remove = current_set - new_set
    tags_to_add = new_set - current_set

    user_tags_result = await session.execute(
        select(Tag.id).where(Tag.user_id == user_id)
    )
    all_tag_ids = set(user_tags_result.scalars().all())

    if not new_set.issubset(all_tag_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'tag_ids',
                'msg': constants.TAGS_NOT_FOUND,
            },
        )

    if tags_to_remove:
        await session.execute(
            delete(task_tag).where(
                and_(
                    task_tag.c.task_id == task_id,
                    task_tag.c.tag_id.in_(tags_to_remove),
                )
            )
        )

    if tags_to_add:
        values_list: list[dict[str, int]] = [
            {'task_id': task_id, 'tag_id': tag_id} for tag_id in tags_to_add
        ]
        await session.execute(insert(task_tag).values(values_list))

    await session.commit()


@connection
async def search_tags(
    user_id: int,
    search_param: str,
    session: AsyncSession,
) -> list[Tag]:
    """Найти все теги пользователя, содержащие поисковую подстроку."""
    result = await session.execute(
        select(Tag)
        .where(Tag.user_id == user_id)
        .filter(Tag.name.icontains(search_param))
    )
    return list(result.scalars().all())
