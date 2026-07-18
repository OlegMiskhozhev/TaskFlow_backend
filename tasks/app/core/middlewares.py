from fastapi import status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from core.config import settings


class ContentTypeCheckMiddleware:
    """ASGI Мидлварь для фильтрации размера и типов запросов на входе."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Динамически подтягиваем карту лимитов и общий лимит из settings
        self._route_limits = settings.FILE_ROUTES_CONFIG
        self._total_limit = settings.TOTAL_UPLOAD_LIMIT

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        method = scope['method']
        path = scope['path']

        if method in ('POST', 'PUT', 'PATCH'):
            headers = dict(scope.get('headers', []))
            content_length_str = headers.get(b'content-length', b'0')

            try:
                content_length = int(content_length_str.decode('utf-8'))
            except ValueError:
                content_length = 0

            # 1. Защита от DDoS: общий лимит на тяжелые POST запросы
            if content_length > self._total_limit:
                response = JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={
                        'error': 'Ошибка валидации данных.',
                        'details': [
                            {
                                'field': 'body',
                                'message': (
                                    'Размер запроса превышает '
                                    'допустимый предел 50 МБ.'
                                ),
                            }
                        ],
                    },
                )
                await response(scope, receive, send)
                return

            # 2. Индивидуальный сетевой отсекатель по карте из settings
            for route, limit in self._route_limits.items():
                if route in path and content_length > limit:
                    response = JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={
                            'error': 'Ошибка валидации данных.',
                            'details': [
                                {
                                    'field': 'file',
                                    'message': (
                                        f'Файл превышает '
                                        f'лимит {limit // (1024 * 1024)} МБ.'
                                    ),
                                }
                            ],
                        },
                    )
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)
