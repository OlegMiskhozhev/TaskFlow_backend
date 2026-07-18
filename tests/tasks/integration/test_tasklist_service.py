import pytest
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.enums import TaskListStatus, TaskStatus
from models.taskflow import Project, Task, TaskList
from services.tasklist import (
    create_tasklist_business_logic,
    reorder_tasklist,
    update_tasklist_business_logic,
)


@pytest.mark.asyncio
class TestTasklistServiceIntegration:
    """Интеграционные тесты сложной бизнес-логики списков задач (Канбан)."""

    async def test_update_tasklist_status_done_cascades_success(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
        create_custom_task_factory,
    ):
        """
        Тест ТЗ: каскадный перевод всех задач колонки в DONE при закрытии.
        """
        project = await create_test_project_factory(test_user)
        tasklist = await create_test_tasklist_factory(
            project_id=project.id, name='Test List', seq_number=1
        )

        t1 = await create_custom_task_factory(
            test_user, status=TaskStatus.IN_PROGRESS
        )
        t1.tasklist_id = tasklist.id

        t2 = await create_custom_task_factory(
            test_user, status=TaskStatus.SCHEDULE
        )
        t2.tasklist_id = tasklist.id

        await db_session.commit()

        # Запоминаем ID до вызова деструктивных методов и закрытия сессий
        t1_id = t1.id
        t2_id = t2.id

        db_session.expunge(project)

        # Вызываем инкапсулированный метод бизнес-логики
        await update_tasklist_business_logic(
            tasklist_id=tasklist.id,
            update_dict={'status': TaskListStatus.DONE},
        )

        # Вычищаем кэш ОЗУ тестовой сессии через close() вместо expire_all()
        await db_session.close()

        for task_id in [t1_id, t2_id]:
            stmt = select(Task).where(Task.id == task_id)
            res = await db_session.execute(stmt)
            task = res.scalar_one()
            assert task.status == TaskStatus.DONE

    async def test_create_tasklist_business_logic_success(
        self, db_session, test_user, create_test_project_factory
    ):
        """Тест: создание списка с автоматическим вычислением seq_number."""
        project = await create_test_project_factory(test_user)

        await create_tasklist_business_logic(
            project_id=project.id,
            tasklist_dict={'name': 'New List', 'status': 'ACTIVE'},
        )

        await db_session.close()
        stmt = select(TaskList).where(TaskList.project_id == project.id)
        res = await db_session.execute(stmt)
        lists = res.scalars().all()

        assert len(lists) == 1
        assert lists[0].name == 'New List'
        assert lists[0].seq_number == 1

    async def test_reorder_tasklist_move_to_front(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: перемещение колонки Drag-and-Drop на самую первую позицию."""
        project = await create_test_project_factory(
            test_user, name='Reorder Project'
        )
        project_id = project.id

        l1 = await create_test_tasklist_factory(project_id, 'List 1', 1)
        l2 = await create_test_tasklist_factory(project_id, 'List 2', 2)
        l3 = await create_test_tasklist_factory(project_id, 'List 3', 3)

        db_session.expunge(project)

        # Вызываем метод переупорядочивания (None вместо previous_id)
        await reorder_tasklist(project, l3.id, None)

        # Очищаем кэш ОЗУ тестовой сессии через close() вместо expire_all()
        await db_session.close()

        # Перечитываем проект с жадной загрузкой обновленных seq_number
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.tasklists))
        )
        res = await db_session.execute(stmt)
        updated_project = res.scalar_one()

        active_lists = [
            tl
            for tl in updated_project.tasklists
            if tl.status == TaskListStatus.ACTIVE
        ]
        active_lists.sort(key=lambda x: x.seq_number)

        # Согласно ТЗ, l3 обязан встать на первую позицию Канбан-доски
        assert active_lists[0].id == l3.id
        assert active_lists[1].id == l1.id
        assert active_lists[2].id == l2.id

    async def test_reorder_tasklist_move_after_another(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: перемещение колонки l1 строго после колонки l3."""
        project = await create_test_project_factory(test_user)
        project_id = project.id

        l1 = await create_test_tasklist_factory(project_id, 'List A', 1)
        l2 = await create_test_tasklist_factory(project_id, 'List B', 2)
        l3 = await create_test_tasklist_factory(project_id, 'List C', 3)

        db_session.expunge(project)

        await reorder_tasklist(project, l1.id, l3.id)

        await db_session.close()

        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.tasklists))
        )
        res = await db_session.execute(stmt)
        updated_project = res.scalar_one()

        active_lists = [
            tl
            for tl in updated_project.tasklists
            if tl.status == TaskListStatus.ACTIVE
        ]
        active_lists.sort(key=lambda x: x.seq_number)

        # Проверяем обновленный порядок индексов в СУБД после рокировки
        assert active_lists[0].id == l2.id
        assert active_lists[1].id == l3.id
        assert active_lists[2].id == l1.id

    async def test_reorder_tasklist_not_found_raises_404(
        self, db_session, test_user, create_test_project_factory
    ):
        """Тест: движение несуществующего списка возвращает 404."""
        project = await create_test_project_factory(test_user)

        db_session.expunge(project)

        with pytest.raises(HTTPException) as exc:
            await reorder_tasklist(project, 99999, None)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_reorder_tasklist_inactive_list_raises_400(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: попытка переместить архивную колонку DONE вызывает 400."""
        project = await create_test_project_factory(test_user)
        inactive_list = await create_test_tasklist_factory(
            project.id, 'Done List', 1
        )
        # Имитируем, что колонка уже закрыта
        inactive_list.status = TaskListStatus.DONE
        await db_session.commit()

        db_session.expunge(project)

        with pytest.raises(HTTPException) as exc:
            await reorder_tasklist(project, inactive_list.id, None)
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_reorder_tasklist_previous_not_found_raises_404(
        self,
        db_session,
        test_user,
        create_test_project_factory,
        create_test_tasklist_factory,
    ):
        """Тест: указание несуществующего соседа-предственника выдает 404."""
        project = await create_test_project_factory(test_user)
        l1 = await create_test_tasklist_factory(project.id, 'List 1', 1)

        db_session.expunge(project)

        with pytest.raises(HTTPException) as exc:
            await reorder_tasklist(project, l1.id, 99999)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
