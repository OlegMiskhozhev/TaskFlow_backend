from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.enums import ProjectStatus, Timezone
from models.taskflow import Project
from schemas.filters import ProjectFilter, ProjectSort, TaskFilter
from schemas.projects import ProjectDetail, ProjectsList
from services.projects import get_project_detail, get_projects


@pytest.mark.asyncio
class TestProjectsServiceIntegration:
    """Интеграционные тесты сложной фильтрации и сортировки проектов."""

    async def test_get_projects_all_statuses(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: получение списка проектов пользователя со всеми статусами."""
        user = await create_test_user_factory(
            email='projects_user@test.com', username='projectsuser'
        )

        await create_test_project_factory(
            test_user=user, name='Project 1', status=ProjectStatus.IN_PROGRESS
        )
        await create_test_project_factory(
            test_user=user, name='Project 2', status=ProjectStatus.ON_PAUSE
        )
        await create_test_project_factory(
            test_user=user, name='Project 3', status=ProjectStatus.DONE
        )

        filters = ProjectFilter(status=[])
        result = await get_projects(user, filters)

        assert isinstance(result, ProjectsList)
        assert len(result.projects) == 3

    async def test_get_projects_sort_by_name_asc(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: лексикографическая сортировка проектов по имени (ASC)."""
        user = await create_test_user_factory(
            email='sort_name@test.com', username='sortname'
        )

        await create_test_project_factory(test_user=user, name='B Project')
        await create_test_project_factory(test_user=user, name='A Project')
        await create_test_project_factory(test_user=user, name='C Project')

        filters = ProjectFilter(order_by=ProjectSort.NAME_ASC)
        result = await get_projects(user, filters)

        # Исправлено AttributeError: обращаемся по индексу массива
        assert result.projects[0].name == 'A Project'
        assert result.projects[1].name == 'B Project'
        assert result.projects[2].name == 'C Project'

    async def test_get_projects_sort_by_name_desc(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: лексикографическая сортировка проектов по имени (DESC)."""
        user = await create_test_user_factory(
            email='sort_name_desc@test.com', username='sortnamedesc'
        )

        await create_test_project_factory(test_user=user, name='A Project')
        await create_test_project_factory(test_user=user, name='C Project')
        await create_test_project_factory(test_user=user, name='B Project')

        filters = ProjectFilter(order_by=ProjectSort.NAME_DESC)
        result = await get_projects(user, filters)

        assert result.projects[0].name == 'C Project'
        assert result.projects[1].name == 'B Project'
        assert result.projects[2].name == 'A Project'

    async def test_get_projects_sort_by_urgent(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: сортировка по срочности (ближайший дедлайн первый)."""
        user = await create_test_user_factory(
            email='sort_urgent@test.com', username='sorturgent'
        )

        now = datetime.now(UTC)
        p_a = await create_test_project_factory(test_user=user, name='Proj A')
        p_a.deadline = now + timedelta(days=10)

        p_b = await create_test_project_factory(test_user=user, name='Proj B')
        p_b.deadline = now + timedelta(days=1)

        p_c = await create_test_project_factory(test_user=user, name='Proj C')
        p_c.deadline = now + timedelta(days=5)

        await db_session.commit()

        filters = ProjectFilter(order_by=ProjectSort.URGENT)
        result = await get_projects(user, filters)

        assert result.projects[0].name == 'Proj B'

    async def test_get_projects_with_all_sort_types(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: проверка сортировки по дате создания CREATED_ASC."""
        user = await create_test_user_factory(
            email='all_sorts@test.com', username='allsorts'
        )

        await create_test_project_factory(test_user=user, name='B Project')
        await create_test_project_factory(test_user=user, name='A Project')

        filters = ProjectFilter(order_by=ProjectSort.CREATED_ASC)
        result = await get_projects(user, filters)
        assert len(result.projects) == 2

    async def test_get_project_detail_success(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: извлечение полной ORM-структуры проекта для Канбан."""
        project_base = await create_test_project_factory(
            test_user=test_user, name='Detail Project'
        )
        tasklist = await create_test_tasklist_factory(
            project_id=project_base.id, name='Test List', seq_number=1
        )

        task1 = await create_custom_task_factory(test_user)
        task1.name = 'Task 1'
        task1.tasklist_id = tasklist.id

        task2 = await create_custom_task_factory(test_user)
        task2.name = 'Task 2'
        task2.tasklist_id = tasklist.id

        await db_session.commit()

        # Насыщаем граф объектов связями, избавляясь от MissingGreenlet
        stmt = (
            select(Project)
            .where(Project.id == project_base.id)
            .options(
                selectinload(Project.tasklists), selectinload(Project.user)
            )
        )
        res = await db_session.execute(stmt)
        project_loaded = res.scalar_one()

        # Полностью очищаем контекст тестовой сессии перед входом в сервис
        db_session.expunge_all()

        # Вызываем транзакционный метод бизнес-логики
        result = await get_project_detail(project_loaded, filters=TaskFilter())

        assert isinstance(result, ProjectDetail)
        assert result.id == project_base.id
        assert result.name == 'Detail Project'
        assert result.user_timezone == Timezone.UTC
        assert len(result.tasklists) == 1
        assert len(result.tasklists[0].tasks) == 2

    async def test_get_projects_sort_by_non_urgent_desc(
        self, db_session, create_test_user_factory, create_test_project_factory
    ):
        """Тест: сортировка NON_URGENT (дальний дедлайн первый)."""
        user = await create_test_user_factory(
            email='non_urgent@test.com', username='nonurgent'
        )

        now = datetime.now(UTC)
        p_near = await create_test_project_factory(test_user=user, name='Near')
        p_near.deadline = now + timedelta(days=1)

        p_mid = await create_test_project_factory(test_user=user, name='Mid')
        p_mid.deadline = now + timedelta(days=15)

        p_far = await create_test_project_factory(test_user=user, name='Far')
        p_far.deadline = now + timedelta(days=30)

        await db_session.commit()

        filters = ProjectFilter(order_by=ProjectSort.NON_URGENT)
        result = await get_projects(user, filters)

        assert result.projects[0].name == 'Far'
        assert result.projects[1].name == 'Mid'
        assert result.projects[2].name == 'Near'
