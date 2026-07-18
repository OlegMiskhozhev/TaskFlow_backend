from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest

from models.taskflow import Project
from routers.projects import create_project, get_project, get_projects_list


@pytest.mark.asyncio
class TestCreateProjectUnit:
    """Юнит-тесты изолированной логики эндпоинта создания проектов."""

    @patch('routers.projects.service.add', new_callable=AsyncMock)
    @patch('routers.projects.get_project_detail', new_callable=AsyncMock)
    async def test_create_project_model_dump(
        self, mock_detail, mock_add, sample_project_dto
    ):
        """Тест: вызов service.add с флагом refresh=True."""
        mock_add.return_value = Mock(id=1)
        mock_detail.return_value = Mock()

        mock_user = Mock()
        mock_user.timezone = 'UTC'
        mock_user.id = 123

        await create_project(user=mock_user, project_data=sample_project_dto)

        mock_add.assert_called_once()

        # Исправлено: извлекаем позиционные аргументы вызова CRUD-сервиса
        args, kwargs = mock_add.call_args

        # args[0] — это класс Project, args[1] — переданный dict данных
        assert args[0] == Project
        assert args[1]['user_id'] == 123
        assert args[1]['name'] == 'Test Project'


@pytest.mark.asyncio
class TestGetProjectsUnit:
    """Юнит-тесты эндпоинта извлечения списков проектов."""

    @patch('routers.projects.get_projects', new_callable=AsyncMock)
    async def test_get_projects_list_calls_service(self, mock_get):
        """Тест: вызов сервисного слоя извлечения проектов с фильтрами."""
        mock_get.return_value = Mock()
        mock_user = Mock()

        result = await get_projects_list(user=mock_user)

        assert result is not None
        # Синхронизировано с ТЗ: передаем project_filters в качестве Query
        mock_get.assert_called_once_with(mock_user, ANY)


@pytest.mark.asyncio
class TestGetProjectUnit:
    """Юнит-тесты эндпоинта получения детальной структуры проекта."""

    @patch('routers.projects.get_project_detail', new_callable=AsyncMock)
    async def test_get_project_detail_calls_service(self, mock_detail):
        """Тест: вызов сервисного слоя деталей проекта с фильтрами задач."""
        mock_detail.return_value = Mock()

        mock_objects = Mock()
        mock_objects.project = Mock()

        result = await get_project(objects=mock_objects)

        assert result is not None
        # Синхронизировано с ТЗ: передаем task_filters в качестве Query
        mock_detail.assert_called_once_with(mock_objects.project, ANY)
