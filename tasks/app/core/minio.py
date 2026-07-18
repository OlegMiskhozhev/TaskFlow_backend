import os
from datetime import timedelta
from typing import BinaryIO

from fastapi.exceptions import RequestValidationError
from minio import Minio
from pydantic import ValidationError


class MinioHandler:
    """Класс для обработки запросов к S3 хранилищу файлов MinIO."""

    def __init__(
        self,
        minio_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        """Установить параметры доступа к хранилищу."""
        self.client: Minio = Minio(
            minio_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket: str = bucket

    async def upload_file(
        self, name: str, file: BinaryIO, length: int
    ) -> bool:
        """Выгрузить файл в хранилище."""
        if self.client.put_object(self.bucket, name, file, length=length):
            return True
        return False

    async def remove_file(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket, object_name)
            return True
        except ValidationError as e:
            raise RequestValidationError(e.errors()) from e
        return False

    async def get_url(self, filename: str) -> str:
        """Получает от MinIO ссылку на скачивание файла из хранилища."""
        url = self.client.get_presigned_url(
            method='GET',
            bucket_name=self.bucket,
            object_name=filename,
            expires=timedelta(hours=2),
        )
        host_url = os.getenv('HOST_URL', 'http://localhost')
        base_host = host_url.rstrip('/')
        external_media_url = f'{base_host}/minio-media'
        scheme = 'https' if self.client._base_url.is_https else 'http'
        internal_base = f'{scheme}://{self.client._base_url.host}'

        return url.replace(internal_base, external_media_url)

    async def check_bucket(self) -> bool:
        """
        Проверить наличие бакета(каталога) в хранилище.

        В случае отсутствия - создать бакет.
        """
        if not self.client.bucket_exists(bucket_name=self.bucket):
            self.client.make_bucket(self.bucket)
        return True
