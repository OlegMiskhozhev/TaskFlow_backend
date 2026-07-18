from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError

from core import exceptions
from core.middlewares import ContentTypeCheckMiddleware
from core.redis import redis_service
from routers.projects import project_router
from routers.users import user_router
from services.attachments import client as attachments_minio
from services.users import client as avatars_minio


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Код при старте сервера
    await attachments_minio.check_bucket()
    await avatars_minio.check_bucket()

    yield

    # Код при остановке сервера (Ctrl+C):
    await redis_service.close()


app = FastAPI(
    root_path='/api/tasks',
    lifespan=lifespan,
    title='TaskFlow',
    description=(
        'Личный таск-трекер с проектами, подзадачами и напоминаниями'
    ),
)


# --- ФУНКЦИЯ РЕГИСТРАЦИИ ХЕНДЛЕРОВ ---
def register_exception_handlers(app_instance: FastAPI) -> None:
    """Привязывает оптимизированные хендлеры к приложению."""
    app_instance.add_exception_handler(
        RequestValidationError, exceptions.validation_exception_handler
    )
    # Регистрируем один хендлер на все контролируемые HTTP-статусы
    app_instance.add_exception_handler(
        status.HTTP_400_BAD_REQUEST, exceptions.http_exception_handler
    )
    app_instance.add_exception_handler(
        status.HTTP_401_UNAUTHORIZED, exceptions.http_exception_handler
    )
    app_instance.add_exception_handler(
        status.HTTP_403_FORBIDDEN, exceptions.http_exception_handler
    )
    app_instance.add_exception_handler(
        status.HTTP_404_NOT_FOUND, exceptions.http_exception_handler
    )
    app_instance.add_exception_handler(
        status.HTTP_405_METHOD_NOT_ALLOWED, exceptions.http_exception_handler
    )
    # Критические ошибки системы
    app_instance.add_exception_handler(
        Exception, exceptions.internal_server_error_handler
    )


# Регистрируем хендлеры
register_exception_handlers(app)


# Подключаем роутеры
app.include_router(project_router)
app.include_router(user_router)


# Подключаем middleware
app.add_middleware(ContentTypeCheckMiddleware)
