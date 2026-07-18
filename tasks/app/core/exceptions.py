import sys
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

# --- НАСТРОЙКА LOGURU ---


logger.remove()
logger.add(
    sys.stdout,
    format='<green>{time:YYYY-MM-DD HH:mm:ss}</green> | '
    '<level>{level: <8}</level> | '
    '<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>',
    level='INFO',
)
logger.add(
    'logs/tasks_errors.log',
    format='{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}',
    rotation='50 MB',
    retention='7 days',
    level='ERROR',
    enqueue=True,
)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


def create_error_response(
    error_type: str, details: list[dict[str, str]], status_code: int
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={'error': error_type, 'details': details},
    )


async def log_exception_short(request: Request, exc: Exception) -> None:
    """Логирует контролируемые ошибки кратко, БЕЗ трейсбэка."""
    query_params = dict(request.query_params)
    log_message = (
        f'[CONTROLLED ERR] {request.method} {request.url.path} | '
        f'Query: {query_params} | Message: {str(exc)}'
    )
    logger.error(log_message)


def parse_http_exception_detail(
    detail: str | dict[str, str] | Any,  # noqa: ANN401
    default_field: str,
) -> list[dict[str, str]]:
    """Автоматически разбирает detail, если он передан как dict."""
    if isinstance(detail, dict):
        return [
            {
                'field': detail.get('field') or default_field,
                'message': detail.get('msg') or str(detail),
            }
        ]
    return [{'field': default_field, 'message': str(detail)}]


# --- ФУНКЦИИ-ХЕНДЛЕРЫ ---


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Глобальный обработчик ошибок валидации Pydantic."""
    await log_exception_short(request, exc)
    details: list[dict[str, str]] = []

    for error in exc.errors():
        # 1. Извлекаем контекст кастомной ошибки PydanticCustomError
        ctx = error.get('ctx', {})

        # 2. Если в контексте есть имя поля — берем его, иначе парсим loc
        if isinstance(ctx, dict) and 'field' in ctx:
            field_name = str(ctx['field'])
        else:
            field_name = (
                str(error['loc'][-1]) if error['loc'] else 'non_field_error'
            )

        details.append(
            {
                'field': field_name,
                'message': error['msg'],
            }
        )

    return create_error_response(
        error_type='Validation Error',
        details=details,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Универсальный хендлер для 400, 401, 403, 404, 405."""
    await log_exception_short(request, exc)

    # Карта дефолтных полей и названий ошибок
    error_mapping = {
        400: ('Bad Request', 'bad_request'),
        401: ('Unauthorized', 'credentials'),
        403: ('Forbidden', 'permissions'),
        404: ('Not Found', 'url_path'),
        405: ('Method Not Allowed', 'request_method'),
    }

    error_type, default_field = error_mapping.get(
        exc.status_code, ('HTTP Error', 'global')
    )

    # Особая логика для 405 (метод не разрешен)
    if exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        details = [
            {
                'field': 'request_method',
                'message': f'Method {request.method} is not allowed.',
            }
        ]
    else:
        # Автоматически вытаскиваем 'field' и 'msg' из словаря
        details = parse_http_exception_detail(exc.detail, default_field)

    return create_error_response(
        error_type=error_type,
        details=details,
        status_code=exc.status_code,
    )


async def internal_server_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """500 ошибка — единственный случай, где нужен ПОЛНЫЙ traceback."""
    query_params = dict(request.query_params)
    body_content: Any = '[Empty or Unreadable]'
    try:
        body_bytes = await request.body()
        if body_bytes:
            body_content = body_bytes.decode('utf-8')
    except Exception:
        pass

    log_message = (
        f'\n[CRITICAL SERVER ERROR IN TASKS]\n'
        f'Path: {request.method} {request.url.path}\n'
        f'Query Params: {query_params}\n'
        f'Body Payload: {body_content}\n'
        f'Error: {str(exc)}'
    )
    # logger.opt(exception=exc) принудительно включает Traceback
    logger.opt(exception=exc).critical(log_message)

    details = [
        {
            'field': 'server',
            'message': 'An unexpected error occurred on the server.',
        }
    ]
    return create_error_response(
        error_type='Internal Server Error',
        details=details,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
