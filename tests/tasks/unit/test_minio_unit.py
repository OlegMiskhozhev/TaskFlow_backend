# tests/tasks/unit/test_minio_handler_unit.py
import os
from datetime import timedelta

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
    """Подавляет глобальную фикстуру изоляции S3-клиента.

    Возвращает исходный экземпляр MinioHandler для контролируемой
    подмены методов put_object и remove_object в юнит-тестах.
    """
    yield


@pytest.mark.asyncio
class TestMinioHandlerUploadFileUnit:
    """Юнит-тесты пайплайнов выгрузки файлов в MinIO S3."""

    async def test_upload_file_success(self, mocker) -> None:
        """Тест: успешная выгрузка бинарного объекта в бакет."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.put_object = mocker.MagicMock(return_value=True)
        mock_file = mocker.Mock()

        result = await handler.upload_file('test.txt', mock_file, 1024)

        assert result is True
        handler.client.put_object.assert_called_once_with(
            'bucket', 'test.txt', mock_file, length=1024
        )

    async def test_upload_file_failure(self, mocker) -> None:
        """Тест: ошибка put_object возвращает False."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.put_object = mocker.MagicMock(return_value=False)
        mock_file = mocker.Mock()

        result = await handler.upload_file('test.txt', mock_file, 1024)
        assert result is False


@pytest.mark.asyncio
class TestMinioHandlerRemoveFileUnit:
    """Юнит-тесты метода remove_file S3-клиента MinIO."""

    async def test_remove_file_success(self, mocker) -> None:
        """Тест: успешное удаление объекта из бакета хранилища."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.remove_object = mocker.MagicMock(return_value=True)

        result = await handler.remove_file('test.txt')

        assert result is True
        handler.client.remove_object.assert_called_once_with(
            'bucket', 'test.txt'
        )

    async def test_remove_file_validation_error_raises_fastapi_exc(
        self, mocker
    ) -> None:
        """Тест: ValidationError перехватывается и трансформируется."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        validation_error = None

        try:
            DummyModel.model_validate(123)
        except ValidationError as e:
            validation_error = e

        handler.client.remove_object = mocker.MagicMock(
            side_effect=validation_error
        )

        with pytest.raises(RequestValidationError) as exc:
            await handler.remove_file('test.txt')

        assert exc.value.errors() == validation_error.errors()


@pytest.mark.asyncio
class TestMinioHandlerGetUrlUnit:
    """Юнит-тесты генерации и подмены ссылок метода get_url."""

    async def test_get_url_replaces_internal_url(self, mocker) -> None:
        """Тест: докер-ссылка заменяется на публичный HOST_URL."""
        handler = MinioHandler(
            'minio-internal-host:9000', 'key', 'secret', 'bucket'
        )

        fake_presigned = (
            'http://minio-internal-host:9000/attachments/test.txt?token=123'
        )
        handler.client.get_presigned_url = mocker.MagicMock(
            return_value=fake_presigned
        )

        handler.client._base_url = mocker.MagicMock()
        handler.client._base_url.is_https = False
        handler.client._base_url.host = 'minio-internal-host:9000'

        mocker.patch.dict(os.environ, {'HOST_URL': 'https://example.com'})
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

    async def test_get_url_with_default_host(self, mocker) -> None:
        """Тест: при отсутствии HOST_URL подставляется localhost."""
        handler = MinioHandler(
            'minio-internal-host:9000', 'key', 'secret', 'bucket'
        )

        fake_presigned = (
            'http://minio-internal-host:9000/attachments/test.txt?token=123'
        )
        handler.client.get_presigned_url = mocker.MagicMock(
            return_value=fake_presigned
        )

        handler.client._base_url = mocker.MagicMock()
        handler.client._base_url.is_https = False
        handler.client._base_url.host = 'minio-internal-host:9000'

        mocker.patch.dict(os.environ, {}, clear=True)
        result = await handler.get_url('test.txt')

        expected_url = (
            'http://localhost/minio-media/attachments/test.txt?token=123'
        )
        assert result == expected_url


@pytest.mark.asyncio
class TestMinioHandlerCheckBucketUnit:
    """Юнит-тесты автоматической инициализации бакетов check_bucket."""

    async def test_check_bucket_exists(self, mocker) -> None:
        """Тест: если бакет создан, make_bucket не вызывается."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.bucket_exists = mocker.MagicMock(return_value=True)
        handler.client.make_bucket = mocker.MagicMock()

        result = await handler.check_bucket()

        assert result is True
        handler.client.bucket_exists.assert_called_once_with(
            bucket_name='bucket'
        )
        handler.client.make_bucket.assert_not_called()

    async def test_check_bucket_not_exists_creates_it(self, mocker) -> None:
        """Тест: если бакета нет, автоматически запускается make_bucket."""
        handler = MinioHandler('localhost:9000', 'key', 'secret', 'bucket')
        handler.client.bucket_exists = mocker.MagicMock(return_value=False)
        handler.client.make_bucket = mocker.MagicMock()

        result = await handler.check_bucket()

        assert result is True
        handler.client.bucket_exists.assert_called_once_with(
            bucket_name='bucket'
        )
        handler.client.make_bucket.assert_called_once_with('bucket')
