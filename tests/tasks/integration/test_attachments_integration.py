from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from sqlalchemy import select

from models.taskflow import Attachment
from services.attachments import (
    attach_attachments_to_task,
    create_attachments,
    remove_attachment,
)


@pytest.mark.asyncio
class TestAttachmentsIntegration:
    """Интеграционные тесты пакетного сохранения и привязки вложений."""

    async def test_create_attachments_multiple_files_success(self, db_session):
        """Тест: пакетное сохранение файлов в S3 и запись структуры в БД."""
        files = []
        for i in range(2):
            mock_file = AsyncMock()
            mock_file.filename = f'test{i}.jpg'
            mock_file.size = 1024
            mock_file.file = BytesIO(b'test data')
            mock_file.read = AsyncMock(return_value=b'test data')
            files.append(mock_file)

        result = await create_attachments(files)

        assert len(result) == 2
        assert result[0].filename == 'test0.jpg'
        assert result[1].filename == 'test1.jpg'
        assert 'fake-s3.local' in result[0].url

    async def test_create_attachments_empty_list(self, db_session):
        """Тест: отправка пустого массива возвращает пустой список."""
        result = await create_attachments([])
        assert result == []

    async def test_attach_attachments_to_task_success(
        self,
        db_session,
        test_user,
        create_test_task_factory,
        create_attachment_factory,
    ):
        """Тест: успешное линкование вложений к задаче в СУБД."""
        task = await create_test_task_factory(test_user)
        att1 = await create_attachment_factory()
        att2 = await create_attachment_factory()

        # Привязываем массив ID к ORM-объекту задачи
        await attach_attachments_to_task(task, [att1.id, att2.id])

        db_session.expire_all()
        await db_session.refresh(task)

        # Проверяем, что связи M2M успешно зафиксировались в PostgreSQL
        assert len(task.attachments) == 2
        attached_ids = {a.id for a in task.attachments}
        assert attached_ids == {att1.id, att2.id}

    async def test_attach_attachments_to_task_already_attached_idempotent(
        self,
        db_session,
        test_user,
        create_test_task_factory,
        create_attachment_factory,
    ):
        """Тест: повторное прикрепление тех же ID не дублирует записи M2M."""
        task = await create_test_task_factory(test_user)
        att = await create_attachment_factory()

        await attach_attachments_to_task(task, [att.id])
        await attach_attachments_to_task(task, [att.id])

        db_session.expire_all()
        await db_session.refresh(task)
        assert len(task.attachments) == 1

    async def test_attach_attachments_to_task_not_found_raises_404(
        self, db_session, test_user, create_test_task_factory
    ):
        """Тест: указание несуществующего ID вложения вызывает 404 по ТЗ."""
        task = await create_test_task_factory(test_user)

        # отсоединяем объект от сессии теста
        db_session.expunge(task)

        with pytest.raises(HTTPException) as exc:
            await attach_attachments_to_task(task, [99999])

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc.value.detail['field'] == 'attachment_id'

    async def test_remove_attachment_success(
        self, db_session, create_attachment_factory
    ):
        """Тест: удаление записи из СУБД и каскадный снос объекта в S3."""
        attachment = await create_attachment_factory()

        # MySql/Postgre Isolation: отсоединяем сущность перед входом в сервис
        db_session.expunge(attachment)

        await remove_attachment(attachment)

        # Возвращаем сессию Pytest в исходное состояние и проверяем СУБД
        db_session.expire_all()
        stmt = select(Attachment).where(Attachment.id == attachment.id)
        db_result = await db_session.execute(stmt)
        assert db_result.scalar_one_or_none() is None
