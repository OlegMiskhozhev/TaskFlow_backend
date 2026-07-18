import os
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio

load_dotenv()


def upload_avatars_to_minio() -> bool:
    """Функция загрузки аватаров в MinIO из папки files/avatars"""

    try:
        client = Minio(
            f'{os.getenv("MINIO_URL")}',
            f'{os.getenv("MINIO_ROOT_USER")}',
            f'{os.getenv("MINIO_ROOT_PASSWORD")}',
            secure=False,
        )

        bucket_name = 'avatars'

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        avatars_dir = Path(__file__).parent / 'files' / 'avatars'

        avatars_map = [
            {
                'local_file': avatars_dir / 'test_1.jpg',
                'minio_name': 'avatar_admin.jpg',
                'content_type': 'image/jpeg',
                'user_id': 1,
                'username': 'admin',
            },
            {
                'local_file': avatars_dir / 'test_2.jpg',
                'minio_name': 'avatar_john.jpg',
                'content_type': 'image/jpeg',
                'user_id': 2,
                'username': 'john_doe',
            },
            {
                'local_file': avatars_dir / 'test_3.jpg',
                'minio_name': 'avatar_jane.jpg',
                'content_type': 'image/jpeg',
                'user_id': 3,
                'username': 'jane_smith',
            },
            {
                'local_file': avatars_dir / 'test_3.jpg',
                'minio_name': 'avatar_bob.jpg',
                'content_type': 'image/jpeg',
                'user_id': 4,
                'username': 'bob_wilson',
            },
            {
                'local_file': avatars_dir / 'test_4.jpg',
                'minio_name': 'avatar_alice.jpg',
                'content_type': 'image/jpeg',
                'user_id': 5,
                'username': 'alice_wonder',
            },
        ]

        uploaded_count = 0
        for avatar in avatars_map:
            if avatar['local_file'].exists():
                client.fput_object(
                    bucket_name,
                    avatar['minio_name'],
                    str(avatar['local_file']),
                    content_type=avatar['content_type'],
                )
        return uploaded_count > 0

    except Exception as e:
        print(f'    ✗ Ошибка загрузки аватаров в MinIO: {e}')
        return False


def upload_files_to_minio() -> bool:
    """Функция загрузки тестовых файлов в MinIO из папки files"""

    try:
        client = Minio(
            f'{os.getenv("MINIO_URL")}',
            f'{os.getenv("MINIO_ROOT_USER")}',
            f'{os.getenv("MINIO_ROOT_PASSWORD")}',
            secure=False,
        )

        bucket_name = 'taskflow'

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        files_dir = Path(__file__).parent / 'files'

        files_map = [
            {
                'local_file': files_dir / 'test_image_1.png',
                'minio_name': 'test_image_456.png',
                'content_type': 'image/png',
                'file_name': 'test_image_1.png',
            },
            {
                'local_file': files_dir / 'test_doc_1.docx',
                'minio_name': 'test_doc_789.docx',
                'content_type': (
                    'application/vnd.openxmlformats-officedocument.'
                    'wordprocessingml.document'
                ),
                'file_name': 'test_doc_1.docx',
            },
        ]

        uploaded_count = 0
        for file_info in files_map:
            if file_info['local_file'].exists():
                client.fput_object(
                    bucket_name,
                    file_info['minio_name'],
                    str(file_info['local_file']),
                    content_type=file_info['content_type'],
                )

        return uploaded_count > 0

    except Exception as e:
        print(f'    ✗ Ошибка загрузки файлов в MinIO: {e}')
        return False
