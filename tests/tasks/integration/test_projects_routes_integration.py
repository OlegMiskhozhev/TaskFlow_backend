import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.enums import ProjectStatus, Timezone
from models.taskflow import Project
from schemas.filters import TaskFilter
from schemas.projects import ProjectDetail
from services.projects import get_project_detail


@pytest.mark.asyncio
class TestProjectsRoutesIntegration:
    """Интеграционные тесты API-эндпоинтов управления проектами."""

    async def test_create_project_success(
        self, async_client, auth_headers, future_datetime_mock
    ):
        """Тест: успешное создание проекта через POST-ручку API."""
        deadline_str = future_datetime_mock.isoformat()

        response = await async_client.post(
            '/projects/',
            json={
                'name': 'Integration Project',
                'description': 'Test Description',
                'deadline': deadline_str,
            },
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['name'] == 'Integration Project'
        assert 'id' in data

    async def test_create_project_unauthenticated_fails(self, async_client):
        """Тест: анонимный запрос блокируется глобальным контуром 401."""
        response = await async_client.post(
            '/projects/', json={'name': 'Unauthorized Project'}
        )

        # Проверяем строгое соответствие JSON-выдаче exceptions.py
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['error'] == 'Unauthorized'
        assert response.json()['details'][0]['field'] == 'credentials'

    async def test_get_projects_list_success(
        self,
        async_client,
        auth_headers,
        test_user,
        create_test_project_factory,
    ):
        """Тест: извлечение массива проектов текущего пользователя."""
        # Оптимизировано: наполнение БД делегировано фабрике из conftest
        for i in range(3):
            await create_test_project_factory(
                test_user=test_user, name=f'Project {i}'
            )

        response = await async_client.get('/projects/', headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'projects' in data
        assert len(data['projects']) >= 3

    async def test_get_projects_list_with_status_filter(
        self,
        async_client,
        auth_headers,
        test_user,
        create_test_project_factory,
    ):
        """Тест: фильтрация вывода по query-параметру status."""
        await create_test_project_factory(
            test_user=test_user,
            name='Active Project',
            status=ProjectStatus.IN_PROGRESS,
        )
        await create_test_project_factory(
            test_user=test_user,
            name='Done Project',
            status=ProjectStatus.DONE,
        )

        # Передаем query-параметр локализованного статуса
        response = await async_client.get(
            '/projects/?status=В работе', headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data['projects']) == 1
        assert data['projects'][0]['name'] == 'Active Project'

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

        stmt = (
            select(Project)
            .where(Project.id == project_base.id)
            .options(
                selectinload(Project.tasklists), selectinload(Project.user)
            )
        )
        res = await db_session.execute(stmt)
        project_loaded = res.scalar_one()

        # Отсоединяем граф объектов от сессии теста, чтобы не было конфликтов
        db_session.expunge_all()

        # Вызываем актуальный транзакционный метод бизнес-логики
        result = await get_project_detail(project_loaded, filters=TaskFilter())

        assert isinstance(result, ProjectDetail)
        assert result.id == project_base.id
        assert result.name == 'Detail Project'
        assert result.user_timezone == Timezone.UTC
        assert len(result.tasklists) == 1
        assert len(result.tasklists[0].tasks) == 2
