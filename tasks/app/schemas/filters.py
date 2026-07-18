from datetime import datetime
from enum import StrEnum

from fastapi import Query
from pydantic import BaseModel

from models.enums import ProjectStatus


class ProjectSort(StrEnum):
    """Варианты сортировки списка проектов."""

    URGENT = 'Срочные'
    NON_URGENT = 'Не срочные'
    CREATED_ASC = 'Старые'
    CREATED_DESC = 'Новые'
    NAME_ASC = 'А-Я'
    NAME_DESC = 'Я-А'


class ProjectFilter(BaseModel):
    """Параметры поиска, фильтрации и сортировки списка проектов."""

    status: list[ProjectStatus] | None = Query(
        default=[], title='Фильтр по статусу'
    )
    q: str | None = Query(default='', title='Поисковая подстрока')
    order_by: ProjectSort | None = Query(default=None, title='Сортировка')


class TaskFilter(BaseModel):
    """Параметры поиска, фильтрации и сортировки задач проекта."""

    q: str | None = Query(default='', title='Поисковая подстрока')
    tag: list[str] = Query(default=[], title='Фильтр по тегам')
    priority: list[str] | None = Query(
        default=None, title='Фильтр по приоритету'
    )
    deadline_from: datetime | None = Query(default=None, title='Дедлайн от')
    deadline_to: datetime | None = Query(default=None, title='Дедлайн до')
