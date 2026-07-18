import os
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError

from core.minio import MinioHandler


class DummyModel(BaseModel):
    """Фиктивная модель для генерации валидного ValidationError."""

    model_config = ConfigDict(extra='forbid')
    dummy_field: str | None = None


@pytest.fixture(scope='function', autouse=True)
def mock_minio_s3_calls():
    """Переопределяет глобальную фикстуру, отключая моки на MinioHandler."""
    yield


@pytest.mark.asyncio
class TestMinioHandlerUploadFileUnit:
    """Юнит-тесты пайплайнов выгрузки файлов в MinIO S3."""

    async def test_upload_file_success(self):
        """Тест: успешная выгрузка бинарного объекта в бакет."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.put_object = MagicMock(return_value=True)
        mock_file = Mock()

        result = await handler.upload_file('test.txt', mock_file, 1024)

        assert result is True
        handler.client.put_object.assert_called_once_with(
            'bucket', 'test.txt', mock_file, length=1024
        )

    async def test_upload_file_failure(self):
        """Тест: ошибка put_object возвращает False."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.put_object = MagicMock(return_value=False)
        mock_file = Mock()

        result = await handler.upload_file('test.txt', mock_file, 1024)
        assert result is False


@pytest.mark.asyncio
class TestMinioHandlerRemoveFileUnit:
    """Юнит-тесты метода remove_file S3-клиента MinIO."""

    async def test_remove_file_success(self):
        """Тест: успешное удаление объекта из бакета хранилища."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.remove_object = MagicMock(return_value=True)

        result = await handler.remove_file('test.txt')

        assert result is True
        handler.client.remove_object.assert_called_once_with(
            'bucket', 'test.txt'
        )

    async def test_remove_file_validation_error_raises_fastapi_exc(self):
        """Тест: ValidationError перехватывается и трансформируется."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')

        try:
            DummyModel(invalid_field='trigger_error')
        except ValidationError as e:
            validation_error = e

        handler.client.remove_object = MagicMock(side_effect=validation_error)

        with pytest.raises(RequestValidationError) as exc:
            await handler.remove_file('test.txt')

        assert exc.value.errors() == validation_error.errors()


@pytest.mark.asyncio
class TestMinioHandlerGetUrlUnit:
    """Юнит-тесты генерации и подмены ссылок метода get_url."""

    async def test_get_url_replaces_internal_url(self):
        """Тест: докер-ссылка заменяется на публичный HOST_URL."""
        handler = MinioHandler(
            'minio-internal-host:9000', 'key', 'secret', 'bucket'
        )

        fake_presigned = (
            'http://minio-internal-host:9000/attachments/test.txt?token=123'
        )
        handler.client.get_presigned_url = MagicMock(
            return_value=fake_presigned
        )

        handler.client._base_url = MagicMock()
        handler.client._base_url.is_https = False
        handler.client._base_url.host = 'minio-internal-host:9000'

        with patch.dict(os.environ, {'HOST_URL': 'https://example.com'}):
            result = await handler.get_url('test.txt')

            expected_url = (
                'https://example.com/minio-media/attachments/'
                'test.txt?token=123'
            )
            assert result == expected_url
            handler.client.get_presigned_url.assert_called_once_with(
                method='GET',
                bucket_name='bucket',
                object_name='test.txt',
                expires=timedelta(hours=2),
            )

    async def test_get_url_with_default_host(self):
        """Тест: при отсутствии HOST_URL подставляется localhost."""
        handler = MinioHandler(
            'minio-internal-host:9000', 'key', 'secret', 'bucket'
        )

        fake_presigned = (
            'http://minio-internal-host:9000/attachments/test.txt?token=123'
        )
        handler.client.get_presigned_url = MagicMock(
            return_value=fake_presigned
        )

        handler.client._base_url = MagicMock()
        handler.client._base_url.is_https = False
        handler.client._base_url.host = 'minio-internal-host:9000'

        with patch.dict(os.environ, {}, clear=True):
            result = await handler.get_url('test.txt')

            expected_url = (
                'http://localhost/minio-media/attachments/test.txt?token=123'
            )
            assert result == expected_url


@pytest.mark.asyncio
class TestMinioHandlerCheckBucketUnit:
    """Юнит-тесты автоматической инициализации бакетов check_bucket."""

    async def test_check_bucket_exists(self):
        """Тест: если бакет создан, make_bucket не вызывается."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.bucket_exists = MagicMock(return_value=True)
        handler.client.make_bucket = MagicMock()

        result = await handler.check_bucket()

        assert result is True
        handler.client.bucket_exists.assert_called_once_with(
            bucket_name='bucket'
        )
        handler.client.make_bucket.assert_not_called()

    async def test_check_bucket_not_exists_creates_it(self):
        """Тест: если бакета нет, автоматически запускается make_bucket."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.bucket_exists = MagicMock(return_value=False)
        handler.client.make_bucket = MagicMock()

        result = await handler.check_bucket()

        assert result is True
        handler.client.bucket_exists.assert_called_once_with(
            bucket_name='bucket'
        )
        handler.client.make_bucket.assert_called_once_with('bucket')
