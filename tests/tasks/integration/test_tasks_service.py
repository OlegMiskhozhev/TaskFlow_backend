import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.taskflow import Project, Task, TaskList
from services.tasks import get_task_detail


@pytest.mark.asyncio
class TestTasksServiceIntegration:
    """Интеграционные тесты бизнес-логики и таймзон карточек задач."""

    async def test_model_validate_and_timezone(
        self, db_session, test_user, create_custom_task_factory
    ):
        """Тест: валидация схемы TaskDetail и проброс таймзоны юзера."""
        task_orm = await create_custom_task_factory(test_user)

        # Жадно подгружаем связи для Pydantic, предотвращая MissingGreenlet
        stmt = (
            select(Task)
            .where(Task.id == task_orm.id)
            .options(
                selectinload(Task.attachments),
                selectinload(Task.tasklist)
                .selectinload(TaskList.project)
                .selectinload(Project.user),
            )
        )
        res = await db_session.execute(stmt)
        task = res.scalar_one()

        db_session.expunge_all()

        # Вызываем сервисный метод получения деталей задачи
        result = await get_task_detail(task)

        assert result is not None
        assert result.id == task_orm.id
        assert result.user_timezone == 'UTC'

    async def test_attachment_url_loop(
        self,
        db_session,
        test_user,
        create_custom_task_factory,
        create_attachment_factory,
    ):
        """Тест: расчет и подстановка внешних MinIO-ссылок в цикле."""
        task_base = await create_custom_task_factory(test_user)
        attachment = await create_attachment_factory()

        # Насыщаем граф объекта связью attachments, предотвращая lazy load
        stmt = (
            select(Task)
            .where(Task.id == task_base.id)
            .options(selectinload(Task.attachments))
        )
        res = await db_session.execute(stmt)
        task_orm = res.scalar_one()

        # Безопасно аппендим вложение в ОЗУ, сокеты не задействуются
        task_orm.attachments.append(attachment)
        await db_session.commit()

        db_session.expunge_all()

        # Вызываем ваш реальный сервисный метод пакетного формирования ссылок
        result = await get_task_detail(task_orm)

        assert result is not None
        assert len(result.attachments) == 1
        assert 'fake-s3.local' in result.attachments[0].url
