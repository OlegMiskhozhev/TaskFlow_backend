import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from loads_to_minio import upload_avatars_to_minio, upload_files_to_minio
from passlib.hash import argon2

CSV_DIR = Path(__file__).parent / 'csv_data'
CSV_DIR.mkdir(exist_ok=True)


def hash_password(password: bytes) -> str:
    """Функция хэширования пароля."""
    return argon2.hash(password)


def create_users_csv() -> Path:
    """
    Функция создания CSV файла users.csv с хэшированными паролями
     на основе email
    """
    file_path = CSV_DIR / 'users.csv'

    users_data = [
        {
            'email': 'admin@example.com',
            'username': 'admin',
            'timezone': 'UTC',
            'is_active': True,
            'role': 'ADMIN',
        },
        {
            'email': 'john@example.com',
            'username': 'john_doe',
            'timezone': 'MOSCOW',
            'is_active': True,
            'role': 'USER',
        },
        {
            'email': 'bob@example.com',
            'username': '11bob_wilson',
            'timezone': 'NEW_YORK',
            'is_active': False,
            'role': 'USER',
        },
    ]

    for user in users_data:
        email = user['email']

        simple_password = email.split('@')[0] + 'Test123!'
        hashed_password = hash_password(simple_password)
        user['password'] = hashed_password

    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'email',
            'password',
            'username',
            'timezone',
            'is_active',
            'role',
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for user in users_data:
            writer.writerow(
                {
                    'email': user['email'],
                    'password': user['password'],
                    'username': user['username'],
                    'timezone': user['timezone'],
                    # CSV формат: true/false
                    'is_active': str(user['is_active']).lower(),
                    'role': user['role'],
                }
            )

    print(f'✅ CSV файл создан: {file_path}')
    return file_path


def create_avatars_csv() -> Path:
    """Функция создания CSV файла avatars.csv и загрузка аватаров в MinIO"""
    file_path = CSV_DIR / 'avatars.csv'

    print('\n  📤 Загрузка аватаров в MinIO:')
    upload_avatars_to_minio()

    data = [
        {
            'filename': 'test_1.jpg',
            'minio_name': 'avatar_admin.jpg',
            'mime_type': 'JPEG',
            'user_id': 1,
        },
        {
            'filename': 'test_2.jpg',
            'minio_name': 'avatar_john.jpg',
            'mime_type': 'JPEG',
            'user_id': 2,
        },
        {
            'filename': 'test_3.jpg',
            'minio_name': 'avatar_jane.jpg',
            'mime_type': 'JPEG',
            'user_id': 3,
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=['filename', 'minio_name', 'mime_type', 'user_id']
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'\n  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_projects_csv() -> Path:
    """Функция создания CSV файла projects.csv согласно модели ProjectStatus"""
    file_path = CSV_DIR / 'projects.csv'

    now = datetime.now(ZoneInfo('UTC'))

    data = [
        {
            'name': 'TaskFlow Web Platform',
            'description': 'Основная веб-платформа для управления задачами',
            'deadline': (now + timedelta(days=30)).isoformat(),  # ← исправлено
            'status': 'IN_PROGRESS',
            'user_id': 1,
            'created_at': (now - timedelta(days=5)).isoformat(),
        },
        {
            'name': 'Mobile App Development',
            'description': (
                'Разработка мобильного приложения для iOS и Android'
            ),
            'deadline': (now + timedelta(days=45)).isoformat(),  # ← исправлено
            'status': 'IN_PROGRESS',
            'user_id': 2,
            'created_at': (now - timedelta(days=1)).isoformat(),
        },
        {
            'name': 'API Integration',
            'description': 'Интеграция с внешними API сервисами',
            'deadline': (now - timedelta(days=5)).isoformat(),  # ← исправлено
            'status': 'DONE',
            'user_id': 2,
            'created_at': (now - timedelta(days=45)).isoformat(),
        },
        {
            'name': 'Database Optimization',
            'description': 'Оптимизация запросов и структуры БД',
            'deadline': (now + timedelta(days=60)).isoformat(),  # ← исправлено
            'status': 'ON_PAUSE',
            'user_id': 1,
            'created_at': (now - timedelta(days=5)).isoformat(),
        },
        {
            'name': 'Legacy System Migration',
            'description': 'Миграция устаревшей системы на новую платформу',
            'deadline': (now - timedelta(days=40)).isoformat(),  # ← исправлено
            'status': 'ARCHIVE',
            'user_id': 1,
            'created_at': (now - timedelta(days=120)).isoformat(),
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'name',
                'description',
                'deadline',
                'status',
                'user_id',
                'created_at',
            ],
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_tasklists_csv() -> Path:
    """Функция создания CSV файла tasklists.csv - без description"""
    file_path = CSV_DIR / 'tasklists.csv'
    data = [
        {
            'name': 'Спринт 1',
            'seq_number': 1,
            'status': 'ACTIVE',
            'project_id': 1,
        },
        {
            'name': 'Спринт 2',
            'seq_number': 2,
            'status': 'ACTIVE',
            'project_id': 1,
        },
        {
            'name': 'Дизайн',
            'seq_number': 1,
            'status': 'ACTIVE',
            'project_id': 3,
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=['name', 'seq_number', 'status', 'project_id']
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f' ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_tasks_csv() -> Path:
    """Функция создания CSV файла tasks.csv согласно модели Task"""
    file_path = CSV_DIR / 'tasks.csv'

    now = datetime.now(ZoneInfo('UTC'))
    data = [
        {
            'name': 'Разработать аутентификацию',
            'description': (
                'Реализовать JWT аутентификацию и регистрацию пользователей'
            ),
            'status': 'IN_PROGRESS',
            'priority': 'HIGH',
            'start_at': '',
            'deadline': (now + timedelta(days=7)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 1,
            'created_at': (now - timedelta(days=5)).isoformat(),
        },
        {
            'name': 'Настроить CI/CD',
            'description': (
                'Настроить автоматическое развертывание через GitHub Actions'
            ),
            'status': 'IN_PROGRESS',
            'priority': 'MID',
            'start_at': '',
            'deadline': (datetime.now() + timedelta(days=14)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 1,
            'created_at': (now - timedelta(days=4)).isoformat(),
        },
        {
            'name': 'Создать дизайн мобильного приложения',
            'description': (
                'Разработать UI/UX дизайн для мобильного приложения'
            ),
            'status': 'DONE',
            'priority': 'HIGH',
            'start_at': '',
            'deadline': (now - timedelta(days=7)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 3,
            'created_at': (now - timedelta(days=6)).isoformat(),
        },
        {
            'name': 'Написать документацию API',
            'description': 'Документировать все эндпоинты API',
            'status': 'DONE',
            'priority': 'LOW',
            'start_at': '',
            'deadline': (now - timedelta(days=12)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 3,
            'created_at': (now - timedelta(days=14)).isoformat(),
        },
        {
            'name': 'Провести код-ревью',
            'description': 'Проверить код всех новых функций',
            'status': 'DONE',
            'priority': 'MID',
            'start_at': (now - timedelta(days=10)).isoformat(),
            'deadline': (now - timedelta(days=7)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 3,
            'created_at': (now - timedelta(days=15)).isoformat(),
        },
        {
            'name': 'Оптимизировать запросы к БД',
            'description': 'Найти и исправить медленные запросы',
            'status': 'IN_PROGRESS',
            'priority': 'HIGH',
            'start_at': (now - timedelta(days=1)).isoformat(),
            'deadline': (now + timedelta(days=10)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 1,
            'created_at': (now - timedelta(days=3)).isoformat(),
        },
        {
            'name': 'Обновить зависимости',
            'description': 'Обновить все пакеты до актуальных версий',
            'status': 'SCHEDULE',
            'priority': 'LOW',
            'start_at': (now + timedelta(days=10)).isoformat(),
            'deadline': (now + timedelta(days=25)).isoformat(),
            'reminder_datetime': '',
            'reminder_periodic': '',
            'tasklist_id': 1,
            'created_at': (now - timedelta(days=1)).isoformat(),
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                'name',
                'description',
                'status',
                'priority',
                'start_at',
                'deadline',
                'reminder_datetime',
                'reminder_periodic',
                'tasklist_id',
                'created_at',
            ],
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def get_file_size(file_path: Path) -> int | None:
    """Функция получения размера файла в байтах"""
    if file_path.exists():
        return file_path.stat().st_size
    return 0


def create_tags_csv() -> Path:
    """Функция создания CSV файла tags.csv"""
    file_path = CSV_DIR / 'tags.csv'
    data = [
        {'name': 'backend', 'user_id': 1},
        {'name': 'frontend', 'user_id': 1},
        {'name': 'urgent', 'user_id': 2},
        {'name': 'bug', 'user_id': 2},
        {'name': 'feature', 'user_id': 1},
        {'name': 'documentation', 'user_id': 3},
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'user_id'])
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_subtasks_csv() -> Path:
    """Функция создания CSV файла subtasks.csv"""
    file_path = CSV_DIR / 'subtasks.csv'
    data = [
        {'name': 'Настроить JWT', 'task_id': 1, 'status': 'IN_PROGRESS'},
        {'name': 'Создать форму регистрации', 'task_id': 1, 'status': 'DONE'},
        {
            'name': 'Настроить GitHub Actions',
            'task_id': 2,
            'status': 'IN_PROGRESS',
        },
        {'name': 'Настроить Docker', 'task_id': 2, 'status': 'DONE'},
        {
            'name': 'Создать главный экран',
            'task_id': 3,
            'status': 'IN_PROGRESS',
        },
        {
            'name': 'Создать экран профиля',
            'task_id': 3,
            'status': 'IN_PROGRESS',
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'task_id', 'status'])
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_attachments_csv() -> Path:
    """Функция создания CSV файла attachments.csv и загрузка файлов в MinIO"""
    file_path = CSV_DIR / 'attachments.csv'

    print('\n  📤 Загрузка файлов в MinIO:')
    upload_files_to_minio()

    data = [
        {
            'filename': 'test_image_1.png',
            'size': get_file_size(
                Path(__file__).parent / 'files' / 'test_image_1.png'
            ),
            'minio_name': 'test_image_456.png',
            'mime_type': 'PNG',
        },
        {
            'filename': 'test_doc_1.docx',
            'size': get_file_size(
                Path(__file__).parent / 'files' / 'test_doc_1.docx'
            ),
            'minio_name': 'test_doc_789.docx',
            'mime_type': 'DOCX',
        },
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=['filename', 'size', 'minio_name', 'mime_type']
        )
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'\n  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_task_tag_csv() -> Path:
    """Функция создания CSV файла task_tag (связующая таблица)"""
    file_path = CSV_DIR / 'task_tag.csv'
    data = [
        {'task_id': 1, 'tag_id': 1},
        {'task_id': 1, 'tag_id': 5},
        {'task_id': 2, 'tag_id': 1},
        {'task_id': 3, 'tag_id': 3},
        {'task_id': 4, 'tag_id': 6},
        {'task_id': 5, 'tag_id': 2},
        {'task_id': 5, 'tag_id': 4},
        {'task_id': 6, 'tag_id': 1},
        {'task_id': 6, 'tag_id': 3},
        {'task_id': 7, 'tag_id': 6},
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['task_id', 'tag_id'])
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path


def create_task_attachments_csv() -> Path:
    """Функция создания CSV файла task_attachments (связующая таблица)"""
    file_path = CSV_DIR / 'task_attachments.csv'
    data = [
        {'task_id': 1, 'attachment_id': 1},
        {'task_id': 1, 'attachment_id': 2},
        {'task_id': 3, 'attachment_id': 2},
        {'task_id': 5, 'attachment_id': 1},
    ]

    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['task_id', 'attachment_id'])
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f'  ✓ Создан {file_path} ({len(data)} записей)')
    return file_path
