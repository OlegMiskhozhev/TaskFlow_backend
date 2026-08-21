# tests/tasks/unit/test_nested_urls_unit.py
import pytest
from fastapi import HTTPException, status

from core.dependency import (
    check_project_url,
    check_subtask_url,
    check_task_url,
    check_tasklist_url,
)
from models.taskflow import Project, Subtask, Task, TaskList


@pytest.mark.asyncio
class TestCheckNestedUrlsUnit:
    """Юнит-тесты функций контроля вложенности URL-сегментов Канбана."""

    async def test_check_project_url_success(self, mocker) -> None:
        """Тест: успешная проверка базового проекта."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mocker.Mock(id=5)
        mock_project = mocker.Mock(user_id=5)
        mock_project.__class__ = Project
        mock_get.return_value = mock_project

        result = await check_project_url(user=mock_user, project_id=1)

        assert result is not None
        assert result.project == mock_project

    async def test_check_project_url_not_found_raises_404(
        self,
        mocker,
    ) -> None:
        """Тест: несуществующий проект возвращает статус 404."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await check_project_url(user=mocker.Mock(), project_id=9999)

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_check_project_url_access_denied_raises_403(
        self,
        mocker,
    ) -> None:
        """Тест: чужой проект блокируется с 403 Forbidden."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mocker.Mock(id=5)
        mock_project = mocker.Mock(user_id=99)  # Чужой ID владельца
        mock_project.__class__ = Project
        mock_get.return_value = mock_project

        with pytest.raises(HTTPException) as exc:
            await check_project_url(user=mock_user, project_id=1)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_check_tasklist_url_success(self, mocker) -> None:
        """Тест: валидация цепочки связей списка задач."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mocker.Mock(id=1)
        mock_tasklist = mocker.MagicMock()
        mock_tasklist.project_id = 10
        mock_tasklist.project.user_id = 1

        # Исправлено is_instance_of: подменяем __class__ для Pydantic v2
        mock_tasklist.__class__ = TaskList
        mock_tasklist.project.__class__ = Project
        mock_get.return_value = mock_tasklist

        result = await check_tasklist_url(
            user=mock_user, project_id=10, tasklist_id=1
        )
        assert result is not None
        assert result.tasklist == mock_tasklist
        assert result.project == mock_tasklist.project

    async def test_check_task_url_success(self, mocker) -> None:
        """Тест: сквозная валидация всей иерархии вложенности карточки."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mocker.Mock(id=1)
        mock_task = mocker.MagicMock()
        mock_task.tasklist_id = 5
        mock_task.tasklist.project_id = 10
        mock_task.tasklist.project.user_id = 1

        # Исправлено: насыщаем иерархию классов для прохождения валидаторов
        mock_task.__class__ = Task
        mock_task.tasklist.__class__ = TaskList
        mock_task.tasklist.project.__class__ = Project
        mock_get.return_value = mock_task

        result = await check_task_url(
            user=mock_user, project_id=10, tasklist_id=5, task_id=1
        )
        assert result is not None
        assert result.task == mock_task
        assert result.tasklist == mock_task.tasklist
        assert result.project == mock_task.tasklist.project

    async def test_check_subtask_url_success(
        self,
        mock_path_hierarchy,
        mocker,
    ) -> None:
        """Тест: успешная сквозная проверка подзадачи через фабрику."""
        mock_get = mocker.patch(
            'core.dependency.service.get',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mocker.Mock(id=1)

        # Фабрика мгновенно строит цепочку связей вложенности
        mock_subtask = mock_path_hierarchy(user_id=1, project_id=1)
        mock_subtask.task_id = 1

        # Исправлено is_instance_of: подменяем __class__ для всей иерархии
        mock_subtask.__class__ = Subtask
        mock_subtask.task.__class__ = Task
        mock_subtask.task.tasklist.__class__ = TaskList
        mock_subtask.task.tasklist.project.__class__ = Project

        mock_get.return_value = mock_subtask

        result = await check_subtask_url(
            user=mock_user,
            project_id=1,
            tasklist_id=1,
            task_id=1,
            subtask_id=1,
        )

        assert result is not None
        assert result.subtask == mock_subtask
        assert result.task == mock_subtask.task
        assert result.tasklist == mock_subtask.task.tasklist
        assert result.project == mock_subtask.task.tasklist.project
