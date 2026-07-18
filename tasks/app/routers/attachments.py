from fastapi import APIRouter, Depends, Response, UploadFile, status

from core.dependency import (
    AttachmentPathDependency,
    AuthDependency,
    TaskPathDependency,
    attachments_files_dependency,
)
from core.redis import redis_service
from schemas.attachments import AttachmentsBind, AttachmentsList
from services.attachments import (
    attach_attachments_to_task,
    create_attachments,
    remove_attachment,
)

attachments_router = APIRouter(prefix='/attachments')
task_attachments_router = APIRouter(prefix='/{task_id}/attachments')

SWAGGER_RESPONSES = {
    404: {
        'description': 'Указанное вложение или задача не найдены.',
        'content': {
            'application/json': {
                'example': {
                    'error': 'Not Found',
                    'details': [
                        {
                            'field': 'attachment_id',
                            'message': 'Файл отсутствует в системе.',
                        }
                    ],
                }
            }
        },
    },
}


@attachments_router.post(
    '/',
    response_model=AttachmentsList,
    status_code=status.HTTP_201_CREATED,
    summary='Загрузить вложения',
)
async def upload_attachments(
    user: AuthDependency,
    files: list[UploadFile] = Depends(attachments_files_dependency),
) -> AttachmentsList:
    attachments = await create_attachments(files)
    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return AttachmentsList(attachments=attachments)


@attachments_router.delete(
    '/{attachment_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить загрузку вложения',
    responses={404: SWAGGER_RESPONSES},
)
@task_attachments_router.delete(
    '/{attachment_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    summary='Удалить загрузку вложения',
    responses={404: SWAGGER_RESPONSES},
)
async def delete_attachments(
    user: AuthDependency,
    attachment: AttachmentPathDependency,
) -> Response:
    await remove_attachment(attachment)
    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@task_attachments_router.post(
    '/',
    status_code=status.HTTP_200_OK,
    summary='Прикрепить вложения к задаче',
    responses={404: SWAGGER_RESPONSES},
)
async def bind_attachment_to_task(
    user: AuthDependency,
    objects: TaskPathDependency,
    attachments: AttachmentsBind,
) -> Response:
    await attach_attachments_to_task(
        task=objects.task,
        attachment_ids=attachments.attachment_ids,
    )
    await redis_service.invalidate(f'user:{user.id}:projects:*')
    return Response(status_code=status.HTTP_200_OK)
