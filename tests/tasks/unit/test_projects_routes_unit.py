import pytest

from models.taskflow import Project
from routers.projects import create_project, get_project, get_projects_list


@pytest.mark.asyncio
class TestCreateProjectUnit:
    """Юнит-тесты изолированной логики эндпоинта создания проектов."""

    async def test_create_project_model_dump(self, sample_project_dto, mocker):
        """Тест: вызов service.add с флагом refresh=True."""
        add_service = mocker.patch(
            'routers.projects.service.add',
            return_value=mocker.Mock(id=1),
            new_callable=mocker.AsyncMock
        )
        mocker.patch(
            'routers.projects.get_project_detail',
            return_value=mocker.Mock(),
            new_callable=mocker.AsyncMock
        )

        mock_user = mocker.Mock()
        mock_user.timezone = 'UTC'
        mock_user.id = 123

        await create_project(user=mock_user, project_data=sample_project_dto)

        add_service.assert_called_once()

        # Исправлено: извлекаем позиционные аргументы вызова CRUD-сервиса
        args = add_service.call_args.args

        # args[0] — это класс Project, args[1] — переданный dict данных
        assert args[0] == Project
        assert args[1]['user_id'] == 123
        assert args[1]['name'] == 'Test Project'


@pytest.mark.asyncio
class TestGetProjectsUnit:
    """Юнит-тесты эндпоинта извлечения списков проектов."""

    async def test_get_projects_list_calls_service(self, mocker):
        """Тест: вызов сервисного слоя извлечения проектов с фильтрами."""
        mock_get = mocker.patch(
            'routers.projects.get_projects',
            return_value=mocker.Mock(),
            new_callable=mocker.AsyncMock,
        )

        mock_user = mocker.Mock()
        result = await get_projects_list(user=mock_user)

        assert result is not None
        # Синхронизировано с ТЗ: передаем project_filters в качестве Query
        mock_get.assert_called_once_with(mock_user, mocker.ANY)


@pytest.mark.asyncio
class TestGetProjectUnit:
    """Юнит-тесты эндпоинта получения детальной структуры проекта."""

    async def test_get_project_detail_calls_service(self, mocker):
        """Тест: вызов сервисного слоя деталей проекта с фильтрами задач."""
        mock_detail = mocker.patch(
            'routers.projects.get_project_detail',
            return_value=mocker.Mock(),
            new_callable=mocker.AsyncMock,
        )

        mock_objects = mocker.Mock()
        mock_objects.project = mocker.Mock()

        result = await get_project(objects=mock_objects)

        assert result is not None
        # Синхронизировано с ТЗ: передаем task_filters в качестве Query
        mock_detail.assert_called_once_with(mock_objects.project, mocker.ANY)
