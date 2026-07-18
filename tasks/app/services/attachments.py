from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.minio import MinioHandler
from database.db import connection
from models.taskflow import Attachment, Task, task_attachments
from schemas.attachments import AttachmentRead

client = MinioHandler(
    settings.minio_settings.MINIO_URL,
    settings.minio_settings.MINIO_ROOT_USER,
    settings.minio_settings.MINIO_ROOT_PASSWORD,
    'attachments',
)


@connection
async def create_attachments(
    files: list[UploadFile], session: AsyncSession
) -> list[AttachmentRead]:
    """Сохранить пакет вложений (Валидация пакета пройдена в зависимости)."""
    results: list[AttachmentRead] = []

    for file in files:
        extension = file.filename.rsplit('.', 1)[-1].lower()
        minio_name = str(uuid4())
        object_name = f'{minio_name}.{extension}'

        # Загружаем бинарные данные напрямую в бакет 'attachments'
        await client.upload_file(object_name, file.file, file.size)

        attachment = Attachment(
            filename=file.filename,
            size=file.size,
            minio_name=minio_name,
            mime_type=extension,  # Записываем чистое расширение
        )
        session.add(attachment)

        # Получаем сгенерированный базой автоинкрементный ID
        await session.flush()

        # Генерируем временную ссылку для фронтенда
        url = await client.get_url(object_name)

        results.append(
            AttachmentRead(
                id=attachment.id,
                filename=attachment.filename,
                size=attachment.size,
                url=url,
            )
        )

    await session.commit()
    return results


@connection
async def attach_attachments_to_task(
    task: Task,
    attachment_ids: list[int],
    session: AsyncSession,
) -> None:
    if attachment_ids:
        query = select(Attachment.id).where(Attachment.id.in_(attachment_ids))
        result = await session.execute(query)
        found_ids = set(result.scalars().all())

        for attachment_id in attachment_ids:
            if attachment_id not in found_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        'type': 'Ошибка доступа.',
                        'field': 'attachment_id',
                        'msg': f'Вложение с id={attachment_id} не найдено.',
                    },
                )

    incoming_ids = set(attachment_ids)

    rel_query = select(task_attachments.c.attachment_id).where(
        task_attachments.c.task_id == task.id
    )
    rel_result = await session.execute(rel_query)
    existing_ids = set(rel_result.scalars().all())

    ids_to_delete = existing_ids - incoming_ids
    if ids_to_delete:
        await session.execute(
            delete(task_attachments).where(
                task_attachments.c.task_id == task.id,
                task_attachments.c.attachment_id.in_(ids_to_delete),
            )
        )

    ids_to_insert = incoming_ids - existing_ids
    if ids_to_insert:
        new_relations = [
            {'task_id': task.id, 'attachment_id': att_id}
            for att_id in ids_to_insert
        ]
        await session.execute(insert(task_attachments).values(new_relations))

    await session.commit()


@connection
async def remove_attachment(
    attachment: Attachment,
    session: AsyncSession,
) -> None:
    await session.delete(attachment)
    await session.commit()

    try:
        await client.remove_file(
            f'{attachment.minio_name}.{attachment.mime_type.value}'
        )
    except Exception:
        pass
