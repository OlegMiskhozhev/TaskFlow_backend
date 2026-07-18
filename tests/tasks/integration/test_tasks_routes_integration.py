from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from models.enums import TaskStatus
from models.taskflow import Reminder, Subtask


@pytest.mark.asyncio
class TestTasksRoutesIntegration:
    """Интеграционные тесты API-эндпоинтов управления задачами."""

    async def test_create_task_success(
        self,
        async_client,
        auth_headers,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: успешное создание базовой задачи через POST-ручку API."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )

        response = await async_client.post(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/',
            json={'name': 'New Task', 'description': 'Test Description'},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

    async def test_create_task_unauthenticated_fails(
        self,
        async_client,
        test_inactive_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: анонимный запрос блокируется глобальным контуром 401."""
        project = await create_test_project_factory(test_inactive_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )

        response = await async_client.post(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/',
            json={'name': 'New Task'},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'Not authenticated' in str(response.json())

    async def test_get_task_detail_success(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: получение полной структуры деталей карточки задачи."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id
        task.name = 'Target Task'

        # Исправлено: фиксация изменений в СУБД перед HTTP-запросом
        await db_session.commit()

        response = await async_client.get(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/{task.id}',
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['name'] == 'Target Task'

    async def test_update_task_success(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: успешная PATCH-модификация текстовых полей карточки."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/{task.id}',
            json={'name': 'Updated Task Name'},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['name'] == 'Updated Task Name'

    async def test_update_task_status_to_done(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: каскадный перевод статуса задачи в DONE."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/'
            f'{task.id}/status',
            json={'status': TaskStatus.DONE.value},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK

        db_session.expire_all()
        await db_session.refresh(task)
        assert task.status == TaskStatus.DONE

    async def test_update_task_status_to_in_progress(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: успешный перевод статуса задачи обратно в IN_PROGRESS."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List'
        )
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/'
            f'{task.id}/status',
            json={'status': TaskStatus.IN_PROGRESS.value},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_move_task_success(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: перенос карточки Drag-and-Drop в другой список проекта."""
        project = await create_test_project_factory(test_user)
        tl1 = await create_test_tasklist_factory(project.id, 'List 1', 1)
        tl2 = await create_test_tasklist_factory(project.id, 'List 2', 2)

        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tl1.id

        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tl1.id}/task/{task.id}/move',
            json={'tasklist_id': tl2.id},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_move_task_not_found_fails(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: перемещение в несуществующую колонку возвращает 404."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(project.id, 'List 1')
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/'
            f'{task.id}/move',
            json={'tasklist_id': 99999},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_task_success(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: окончательное каскадное удаление карточки задачи."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(project.id, 'List 1')
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        response = await async_client.delete(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/{task.id}',
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

    async def test_update_task_period_success(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """Тест: изменение дат начала и дедлайна карточки задачи."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(project.id, 'List 1')
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        await db_session.commit()

        start_str = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        end_str = (datetime.now(UTC) + timedelta(days=10)).isoformat()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/'
            f'{task.id}/period',
            json={'start_at': start_str, 'deadline': end_str},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_update_task_status_to_done_with_subtasks(
        self,
        async_client,
        auth_headers,
        test_user,
        db_session,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
        create_test_reminder_factory,
    ):
        """Тест ТЗ: каскадное закрытие подзадач и снос очереди алертов."""
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(project.id, 'List 1')
        task = await create_custom_task_factory(test_user)
        task.tasklist_id = tasklist.id

        subtask = Subtask(
            name='Subtask 1', task_id=task.id, status='IN_PROGRESS'
        )
        db_session.add(subtask)

        past_time = datetime.now(UTC) + timedelta(days=1)
        await create_test_reminder_factory(
            task_id=task.id, send_time=past_time
        )
        await db_session.commit()

        response = await async_client.patch(
            f'/projects/{project.id}/tasklist/{tasklist.id}/task/'
            f'{task.id}/status',
            json={'status': TaskStatus.DONE.value},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK

        db_session.expire_all()
        await db_session.refresh(task)
        await db_session.refresh(subtask)

        assert task.status == TaskStatus.DONE
        assert subtask.status == 'Завершено'

        stmt = select(Reminder).where(Reminder.task_id == task.id)
        db_res = await db_session.execute(stmt)
        assert db_res.scalar_one_or_none() is None
