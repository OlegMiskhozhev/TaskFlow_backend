import os
import re
from enum import StrEnum
from typing import Annotated, Any

import filetype
from fastapi import (
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import constants
from core.config import settings
from models.enums import AvatarMIMEType, MIMEType
from models.taskflow import (
    Attachment,
    Project,
    Reminder,
    Subtask,
    Tag,
    Task,
    TaskList,
)
from models.users import Token, User
from schemas.core import PathObjects
from services.auth import auth_service
from services.base import service
from services.users import get_user_by_token

security = HTTPBearer()

ACCESS_DENIED = {
    'type': 'Ошибка доступа.',
    'field': '',
    'msg': constants.ACCESS_DENIED,
}


# --- АУТЕНТИФИКАЦИЯ ---


async def is_authenticate(
    token_data: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """Аутентифицировать текущего пользователя по JWT токену."""
    token: str = token_data.credentials
    payload: dict[str, Any] = await auth_service.jwt.verify_token_payload(
        token, 'access'
    )
    token_object: Token = await auth_service.jwt.get_token_by_access(token)
    user: User = await get_user_by_token(token)

    if (
        not user
        or not user.is_active
        or user.id != payload.get('user_id')
        or not token
        or not token_object.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                'type': 'Ошибка авторизации.',
                'field': '',
                'msg': constants.ACCESS_ERROR,
            },
        )
    return user


AuthDependency = Annotated[User, Depends(is_authenticate)]


# --- ЗАВИСИМОСТИ ПУТЕЙ НА БАЗЕ SERVICE.GET() ---


async def check_reminder_url(
    user: AuthDependency,
    reminder_id: int = Path(title='Идентификатор напоминания'),
) -> Reminder:
    """Проверить напоминание."""
    reminder: Reminder = await service.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'reminder_id',
                'msg': constants.REMINDER_NOT_FOUND,
            },
        )

    if reminder.task.tasklist.project.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED
        )

    return reminder


ReminderPathDependency = Annotated[Reminder, Depends(check_reminder_url)]


async def check_tag_url(
    user: AuthDependency,
    tag_id: int = Path(title='Идентификатор тега'),
) -> Tag:
    """Проверить тег."""
    tag: Tag = await service.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'tag_id',
                'msg': constants.TAGS_NOT_FOUND,
            },
        )

    if tag.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED
        )

    return tag


TagPathDependency = Annotated[Tag, Depends(check_tag_url)]


async def check_attachment_url(
    user: AuthDependency,
    attachment_id: int = Path(title='Идентификатор вложения'),
) -> Attachment:
    """Проверить вложение."""
    attachment: Attachment = await service.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'attachment_id',
                'msg': constants.ATTACHMENT_NOT_FOUND,
            },
        )
    return attachment


AttachmentPathDependency = Annotated[Attachment, Depends(check_attachment_url)]


async def check_project_url(
    user: AuthDependency,
    project_id: int = Path(title='Идентификатор проекта'),
) -> PathObjects:
    """Проверить проект."""
    project: Project = await service.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'project_id',
                'msg': constants.PROJECT_NOT_FOUND,
            },
        )

    if project.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ACCESS_DENIED
        )

    return PathObjects(project=project)


ProjectPathDependency = Annotated[PathObjects, Depends(check_project_url)]


async def check_tasklist_url(
    user: AuthDependency,
    project_id: int = Path(title='Идентификатор проекта'),
    tasklist_id: int = Path(title='Идентификатор списка задач'),
) -> PathObjects:
    """Проверить список задач."""
    tasklist: TaskList = await service.get(TaskList, tasklist_id)
    if (
        not tasklist
        or tasklist.project_id != project_id
        or tasklist.project.user_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'tasklist_id',
                'msg': constants.TASKLIST_NOT_FOUND,
            },
        )

    return PathObjects(project=tasklist.project, tasklist=tasklist)


TaskListPathDependency = Annotated[PathObjects, Depends(check_tasklist_url)]


async def check_task_url(
    user: AuthDependency,
    project_id: int = Path(title='Идентификатор проекта'),
    tasklist_id: int = Path(title='Идентификатор списка задач'),
    task_id: int = Path(title='Идентификатор задачи'),
) -> PathObjects:
    """Проверить задачу."""
    task: Task = await service.get(Task, task_id)
    if (
        not task
        or task.tasklist_id != tasklist_id
        or task.tasklist.project_id != project_id
        or task.tasklist.project.user_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'task_id',
                'msg': constants.TASK_NOT_FOUND,
            },
        )

    return PathObjects(
        project=task.tasklist.project, tasklist=task.tasklist, task=task
    )


TaskPathDependency = Annotated[PathObjects, Depends(check_task_url)]


async def check_subtask_url(
    user: AuthDependency,
    project_id: int = Path(title='Идентификатор проекта'),
    tasklist_id: int = Path(title='Идентификатор списка задач'),
    task_id: int = Path(title='Идентификатор задачи'),
    subtask_id: int = Path(title='Идентификатор подзадачи'),
) -> PathObjects:
    """Проверить подзадачу."""
    subtask: Subtask = await service.get(Subtask, subtask_id)
    if (
        not subtask
        or subtask.task_id != task_id
        or subtask.task.tasklist_id != tasklist_id
        or subtask.task.tasklist.project_id != project_id
        or subtask.task.tasklist.project.user_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'type': 'Ошибка доступа',
                'field': 'subtask_id',
                'msg': constants.SUBTASK_NOT_FOUND,
            },
        )

    return PathObjects(
        project=subtask.task.tasklist.project,
        tasklist=subtask.task.tasklist,
        task=subtask.task,
        subtask=subtask,
    )


SubtaskPathDependency = Annotated[PathObjects, Depends(check_subtask_url)]


# --- ФАЙЛОВЫЕ ЗАВИСИМОСТИ ---


async def _validate_file_core(
    file: UploadFile,
    allow_file_size: int,
    expected_types: list[str],
    allow_extensions: type[StrEnum],
) -> None:
    """Пайплайн двойной валидации (Белый + Черный списки из settings)."""
    if not file.filename or '.' not in file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': constants.NOT_ALLOWED_FILE_NAME,
            },
        )

    filename_cleaned = os.path.basename(file.filename)

    if file.size and file.size > allow_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': constants.NOT_ALLOWED_FILE_SIZE,
            },
        )

    # Разбираем имя на составные части по точкам
    filename_parts = filename_cleaned.split('.')
    final_extension = filename_parts[-1].lower()
    intermediate_parts = [part.lower() for part in filename_parts[1:-1]]

    # =================================================================
    # КОНТУР 1. ВЕРИФИКАЦИЯ ЧЕРНОГО СПИСКА (Защита от маскировки)
    # =================================================================

    # Проверяем финальное расширение по черному списку (file.png.exe)
    if final_extension in settings.DANGEROUS_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка безопасности',
                'field': 'file',
                'msg': 'Загрузка исполняемых файлов категорически запрещена.',
            },
        )

    # Проверяем все промежуточные расширения (file.exe.png)
    if any(ext in settings.DANGEROUS_EXTENSIONS for ext in intermediate_parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка безопасности',
                'field': 'file',
                'msg': 'Обнаружена попытка маскировки исполняемого файла.',
            },
        )

    # =================================================================
    # КОНТУР 2. ВЕРИФИКАЦИЯ БЕЛОГО СПИСКА (Строго по вашему ТЗ)
    # =================================================================

    # Проверка финального расширения на соответствие ТЗ
    try:
        allow_extensions(final_extension)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': constants.NOT_ALLOWED_FILE_EXTENTION,
            },
        ) from None

    # Умный контроль промежуточных расширений по вашей логике белого списка
    if intermediate_parts:
        valid_extensions = {item.value.lower() for item in allow_extensions}
        for part in intermediate_parts:
            if (
                not part.isdigit()
                and not re.match(r'^v\d+$', part)
                and part not in valid_extensions
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        'type': 'Ошибка безопасности',
                        'field': 'file',
                        'msg': 'Обнаружено подозрительное двойное расширение.',
                    },
                )

    # =================================================================
    # КОНТУР 3. БИНАРНАЯ ПРОВЕРКА СИГНАТУРЫ БАЙТ
    # =================================================================

    header_chunk = await file.read(2048)
    kind = filetype.guess(header_chunk)
    await file.seek(0)

    if kind is not None:
        file_type = kind.mime
    else:
        try:
            header_chunk.decode('utf-8')
            file_type = 'text/plain'
        except UnicodeDecodeError:
            file_type = 'application/octet-stream'

    if file_type in (
        'application/x-msdownload',
        'application/x-executable',
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                'type': 'Ошибка безопасности',
                'field': 'file',
                'msg': 'Загрузка исполняемых файлов категорически запрещена.',
            },
        )

    if file_type not in expected_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': constants.NOT_ALLOWED_FILE_TYPE,
            },
        )


async def avatar_file_dependency(
    # Принудительно просим FastAPI собрать ВСЕ файлы с ключом 'file' в список
    file: list[UploadFile] = File(None, description='Файл аватара'),
) -> UploadFile:
    """Зависимость для загрузки аватара."""
    # 1. Если поле вообще отсутствует в запросе
    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': 'Файл аватара не выбран.',
            },
        )

    # 2. Жесткое выполнение ТЗ: если файлов больше одного
    if len(file) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': 'Нельзя загрузить несколько файлов на аватар.',
            },
        )

    # Забираем единственный целевой файл из списка
    target_file = file[0]

    # 3. Защита от пустых текстовых полей и файлов без имени
    # В списках File() пустые текстовые поля ловятся проверкой размера и имени
    if not target_file.filename or target_file.filename == '':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'file',
                'msg': 'Файл аватара не выбран или передан неверный формат.',
            },
        )

    # Глубокая трехконтурная проверка (Белый + Черный списки + Бинарный сканер)
    await _validate_file_core(
        file=target_file,
        allow_file_size=settings.AVATAR_ALLOWABLE_FILE_SIZE,
        expected_types=settings.AVATAR_ALLOWABLE_FILE_TYPE,
        allow_extensions=AvatarMIMEType,
    )

    return target_file


async def attachments_files_dependency(
    # Для списка вложений мы явно просим FastAPI собрать список объектов
    files: list[Any] = Form(None, description='Список файлов вложений'),
) -> list[UploadFile]:
    """Зависимость для ручки вложений: список валидных файлов."""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'files',
                'msg': 'Список файлов для загрузки пуст.',
            },
        )

    validated_files = []
    for item in files:
        if isinstance(item, str) or item.filename == '':
            continue

        await _validate_file_core(
            file=item,
            allow_file_size=settings.ATTACHMENT_ALLOWABLE_FILE_SIZE,
            expected_types=settings.ATTACHMENT_ALLOWABLE_FILE_TYPE,
            allow_extensions=MIMEType,
        )
        validated_files.append(item)

    if not validated_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'type': 'Ошибка валидации',
                'field': 'files',
                'msg': 'Не передано ни одного валидного файла.',
            },
        )

    return validated_files
