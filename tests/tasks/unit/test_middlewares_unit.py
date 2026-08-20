from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from core.middlewares import ContentTypeCheckMiddleware


class TestContentTypeCheckMiddlewareUnit:
    """Юнит-тесты сетевого middleware ContentTypeCheckMiddleware."""

    def _create_app(self):
        """Создаёт тестовое приложение со сквозным middleware."""
        app = FastAPI()
        app.add_middleware(ContentTypeCheckMiddleware)

        @app.post('/user/avatar')
        async def avatar_endpoint():
            return {'message': 'avatar ok'}

        @app.post('/projects/attachments/')
        async def attachments_endpoint():
            return {'message': 'attachments ok'}

        @app.post('/api/other')
        async def other_endpoint():
            return {'message': 'ok'}

        return app

    def test_valid_request_sizes_pass_successfully(self):
        """Тест: запросы в рамках лимитов успешно пропускаются."""
        app = self._create_app()
        client = TestClient(app)

        # Отправляем маленький аватар (100 байт) - лимит 2 МБ
        response = client.post(
            '/user/avatar',
            headers={'Content-Length': '100'},
        )
        assert response.status_code == 200
        assert response.json() == {'message': 'avatar ok'}

        # Отправляем маленькое вложение (1 КБ) - лимит 10 МБ
        response = client.post(
            '/projects/attachments/',
            headers={'Content-Length': '1024'},
        )
        assert response.status_code == 200
        assert response.json() == {'message': 'attachments ok'}

    def test_avatar_route_size_exceeded_returns_413(self, mocker):
        """Тест: аватар тяжелее индивидуального лимита возвращает 413."""
        mock_settings = mocker.patch('core.middlewares.settings')
        mock_settings.TOTAL_UPLOAD_LIMIT = 50 * 1024 * 1024
        mock_settings.FILE_ROUTES_CONFIG = {
            '/user/avatar': 2 * 1024 * 1024,
        }

        app = self._create_app()
        client = TestClient(app)

        # Передаем размер 3 МБ (превышает индивидуальный лимит 2 МБ)
        response = client.post(
            '/user/avatar',
            headers={'Content-Length': str(3 * 1024 * 1024)},
        )
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert 'Файл превышает лимит 2 МБ' in response.text

    def test_attachments_route_size_exceeded_returns_413(self, mocker):
        """Тест: вложение тяжелее 10 МБ возвращает 413."""
        mock_settings = mocker.patch('core.middlewares.settings')
        mock_settings.TOTAL_UPLOAD_LIMIT = 50 * 1024 * 1024
        mock_settings.FILE_ROUTES_CONFIG = {
            '/projects/attachments/': 10 * 1024 * 1024,
        }

        app = self._create_app()
        client = TestClient(app)

        # Передаем размер 11 МБ (превышает индивидуальный лимит 10 МБ)
        response = client.post(
            '/projects/attachments/',
            headers={'Content-Length': str(11 * 1024 * 1024)},
        )
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert 'Файл превышает лимит 10 МБ' in response.text

    def test_global_total_limit_exceeded_returns_413(self, mocker):
        """Тест: любой POST-запрос тяжелее 50 МБ блокируется."""
        mock_settings = mocker.patch('core.middlewares.settings')
        mock_settings.TOTAL_UPLOAD_LIMIT = 50 * 1024 * 1024
        mock_settings.FILE_ROUTES_CONFIG = {}

        app = self._create_app()
        client = TestClient(app)

        # Любая посторонняя ручка, куда заливают 51 МБ мусора
        response = client.post(
            '/api/other',
            headers={'Content-Length': str(51 * 1024 * 1024)},
        )
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert 'Размер запроса превышает допустимый предел' in response.text

