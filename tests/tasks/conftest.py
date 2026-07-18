import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# 1. Мгновенная инициализация путей для предотвращения ImportError
ROOT_DIR = Path(__file__).resolve().parents[2]
TASKS_APP_DIR = ROOT_DIR / 'tasks' / 'app'

if str(TASKS_APP_DIR) not in sys.path:
    sys.path.insert(0, str(TASKS_APP_DIR))

from main import app

import core.redis as app_redis
import database.db as db_module
import services.users as users_service
from database.db import Base
from models.enums import (
    ProjectStatus,
    ReminderChannel,
    ReminderStatus,
    TaskPriority,
    TaskStatus,
    Timezone,
    UserRole,
)
from models.taskflow import (
    Attachment,
    Project,
    Reminder,
    Tag,
    Task,
    TaskList,
)
from models.users import Token, User
from schemas.projects import ProjectCreate
from schemas.users import RegisterRequest
from services.auth import auth_service

DB_USER = os.getenv('TASKS_DB_USER')
DB_PASS = os.getenv('TASKS_DB_PASSWORD')
DB_HOST = os.getenv('TASKS_DB_HOST')
DB_PORT = os.getenv('TASKS_DB_PORT')
DB_NAME = os.getenv('TASKS_DB')

ASYNC_URL = (
    f'postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)


@pytest_asyncio.fixture(scope='function', autouse=True)
async def manage_db():
    """Атомарно пересоздает чистую тестовую базу СУБД перед каждым тестом."""
    conn = await asyncpg.connect(
        user=DB_USER,
        password=DB_PASS,
        database='postgres',
        host=DB_HOST,
        port=DB_PORT,
    )
    await conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{DB_NAME}'
    """)
    exists = await conn.fetchval(
        'SELECT 1 FROM pg_database WHERE datname = $1', DB_NAME
    )
    if exists:
        await conn.execute(f'DROP DATABASE "{DB_NAME}"')
    await conn.execute(f'CREATE DATABASE "{DB_NAME}"')
    await conn.close()

    yield

    conn = await asyncpg.connect(
        user=DB_USER,
        password=DB_PASS,
        database='postgres',
        host=DB_HOST,
        port=DB_PORT,
    )
    await conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{DB_NAME}'
    """)
    await conn.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')
    await conn.close()


@pytest_asyncio.fixture(scope='function')
async def db_engine(manage_db):
    """Инициализирует тестовый движок SQLAlchemy и создает таблицы."""
    engine = create_async_engine(ASYNC_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_maker(db_engine):
    """Создает тестовую фабрику сессий async_sessionmaker."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ─────────────────────────────────────────────────────────────────
# SECTION 1: УПРАВЛЕНИЕ СЕССИЯМИ СУБД И ИЗОЛЯЦИЯ ТРАНЗАКЦИЙ
# ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def override_session_maker(test_session_maker):
    """Подменяет глобальную фабрику сессий приложения на тестовую."""
    original_session_maker = db_module.async_session_maker
    db_module.async_session_maker = test_session_maker
    try:
        yield
    finally:
        db_module.async_session_maker = original_session_maker


@pytest_asyncio.fixture
async def db_session(test_session_maker):
    """Создаёт изолированную контекстную сессию БД для тестов."""
    async with test_session_maker() as session:
        yield session


@pytest.fixture
def force_commit_failure(monkeypatch: pytest.MonkeyPatch):
    """Позволяет принудительно вызывать сбой коммита транзакции в СУБД."""

    def _activate() -> None:
        async def _fail_commit(_self) -> None:
            raise SQLAlchemyError('commit failed')

        monkeypatch.setattr(AsyncSession, 'commit', _fail_commit)

    return _activate


# ─────────────────────────────────────────────────────────────────
# SECTION 2: ПРОФИЛИ ТЕСТОВЫХ ПОЛЬЗОВАТЕЛЕЙ И АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_user(db_session):
    """Создаёт и фиксирует в СУБД активного тестового пользователя."""
    hashed_pass = await auth_service.crypto.hash_password('Test123!^*Test')
    user = User(
        email='test@test.com',
        password=hashed_pass,
        timezone=Timezone.UTC,
        is_active=True,
        username='testuser',
        role=UserRole.USER,
        is_blocked=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_inactive_user(db_session):
    """Создаёт и фиксирует в СУБД неактивного тестового пользователя."""
    hashed_pass = await auth_service.crypto.hash_password('Test123!^*Test')
    user = User(
        email='inactive@test.com',
        password=hashed_pass,
        timezone=Timezone.UTC,
        is_active=False,
        username='inactiveuser',
        role=UserRole.USER,
        is_blocked=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    """Создаёт валидные заголовки авторизации на базе JWT токена."""
    tokens = await auth_service.jwt.create_token_pair(test_user.id)
    return {'Authorization': f'Bearer {tokens["access_token"]}'}


@pytest_asyncio.fixture
async def async_client():
    """Инициализирует асинхронный тестовый клиент HTTP-запросов FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        yield ac


@pytest.fixture
def mock_send_confirmation_email():
    """Мокает отложенную Celery-таску отправки email подтверждения."""
    with patch('routers.auth.send_confirmation_email_task.delay') as mock:
        yield mock


@pytest.fixture
def mock_send_password_reset_email():
    """Мокает отложенную Celery-таску отправки email сброса пароля."""
    with patch('routers.auth.send_password_reset_email_task.delay') as mock:
        yield mock


# ─────────────────────────────────────────────────────────────────
# SECTION 3: СЕТЕВАЯ ИНФРАСТРУКТУРА И КЭШИРОВАНИЕ (REDIS, S3 MINIO)
# ─────────────────────────────────────────────────────────────────


# Прямая инжекция пустых асинхронных функций в оригинальные синглтоны
async def dummy_redis_call(*args, **kwargs):
    """Бесшумная заглушка, заменяющая вызовы к Redis в роутерах API."""
    return True


async def dummy_redis_get(*args, **kwargs):
    """Бесшумный геттер, имитирующий cache miss для тестов."""
    return None


app_redis.redis_service.invalidate = dummy_redis_call
app_redis.redis_service.get = dummy_redis_get
app_redis.redis_service.set = dummy_redis_call
app_redis.redis_service.delete = dummy_redis_call

users_service.redis_cache.invalidate = dummy_redis_call
users_service.redis_cache.get = dummy_redis_get
users_service.redis_cache.set = dummy_redis_call
users_service.redis_cache.delete = dummy_redis_call


@pytest_asyncio.fixture(scope='function', autouse=True)
async def clear_redis_cache():
    """Автоматически очищает Redis между тестами для изоляции кэша."""
    yield


@pytest.fixture(scope='function', autouse=True)
def mock_minio_s3_calls():
    """Полностью изолирует вызовы сетевого клиента MinIO Handler."""
    with (
        patch(
            'core.minio.MinioHandler.upload_file',
            new_callable=AsyncMock,
        ) as mock_upload,
        patch(
            'core.minio.MinioHandler.remove_file',
            new_callable=AsyncMock,
        ) as mock_remove,
        patch(
            'core.minio.MinioHandler.get_url',
            new_callable=AsyncMock,
        ) as mock_url,
    ):
        mock_upload.return_value = True
        mock_remove.return_value = True
        mock_url.return_value = 'http://fake-s3.local'
        yield


@pytest.fixture(autouse=True)
def mock_redis_service_global():
    """Глобальный авто-патч на Redis-сервис для всех тестов."""
    mock_service = AsyncMock()
    mock_service.get.return_value = None
    mock_service.set.return_value = True
    mock_service.delete.return_value = True
    mock_service.invalidate.return_value = True
    yield mock_service


# ─────────────────────────────────────────────────────────────────
# SECTION 4: ЛЕГКОВЕСНЫЕ СХЕМЫ, ХЕЛПЕРЫ ДАТ И ИЕРАРХИИ ПУТЕЙ
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def future_datetime_mock() -> datetime:
    """Генерирует детерминированную будущую дату для дедлайнов ТЗ."""
    return datetime.now(UTC) + timedelta(days=30)


@pytest.fixture
def sample_project_dto(future_datetime_mock) -> ProjectCreate:
    """Генерирует чистый дефолтный DTO создания проекта."""
    return ProjectCreate(name='Test Project', deadline=future_datetime_mock)


@pytest.fixture
def sample_register_dto() -> RegisterRequest:
    """Генерирует чистый дефолтный DTO регистрации пользователя."""
    return RegisterRequest(
        email='new_user@test.com',
        password='Test123!^*Test',
        confirm_password='Test123!^*Test',
    )


@pytest.fixture
def mock_path_hierarchy():
    """Фабрика для генерации мок-иерархии сущностей PathObjects."""

    def _create(user_id: int, project_id: int = 1) -> MagicMock:
        mock_subtask = MagicMock()
        mock_subtask.task_id = 1
        mock_subtask.task.tasklist_id = 1
        mock_subtask.task.tasklist.project_id = project_id
        mock_subtask.task.tasklist.project.user_id = user_id
        return mock_subtask

    return _create


# ─────────────────────────────────────────────────────────────────
# SECTION 5: ПРОМЫШЛЕННЫЕ ORM-ФАБРИКИ (FIXTURE FACTORIES) СУБД
# ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
def create_test_user_factory(db_session):
    """Фабрика для генерации уникальных ORM-пользователей в тестах СУБД."""

    async def _create(
        email: str, username: str, is_active: bool = True
    ) -> User:
        hashed_pass = await auth_service.crypto.hash_password('hash123')
        user = User(
            email=email,
            password=hashed_pass,
            timezone=Timezone.UTC,
            is_active=is_active,
            username=username,
            role=UserRole.USER,
            is_blocked=False,
        )
        db_session.add(user)
        await db_session.commit()
        return user

    return _create


@pytest_asyncio.fixture
def create_test_token_factory(db_session):
    """Фабрика для генерации ORM-объектов сессий токенов в СУБД."""

    async def _create(
        user_id: int, access_token: str, is_active: bool = True
    ) -> Token:
        token = Token(
            access_token=access_token,
            refresh_token=f'{access_token}_refresh',
            user_id=user_id,
            is_active=is_active,
        )
        db_session.add(token)
        await db_session.commit()
        return token

    return _create


@pytest_asyncio.fixture
def create_test_project_factory(db_session, future_datetime_mock):
    """Фабрика для генерации ORM-объектов проектов в тестовой СУБД."""

    async def _create(
        test_user,
        name: str = 'Test Project',
        status: ProjectStatus = ProjectStatus.IN_PROGRESS,
    ) -> Project:
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        project = Project(
            name=name,
            user_id=test_user.id,
            status=status,
            deadline=future_datetime_mock,
            created_at=now_naive,
        )
        db_session.add(project)
        await db_session.commit()
        return project

    return _create


@pytest_asyncio.fixture
def create_test_tasklist_factory(db_session):
    """Фабрика для генерации ORM-объектов списков задач в тестовой СУБД."""

    async def _create(
        project_id: int, name: str, seq_number: int = 1
    ) -> TaskList:
        tasklist = TaskList(
            name=name,
            project_id=project_id,
            seq_number=seq_number,
            status='Активный',
        )
        db_session.add(tasklist)
        await db_session.commit()
        return tasklist

    return _create


@pytest_asyncio.fixture
def create_test_task_factory(db_session, future_datetime_mock):
    """Фабрика для быстрой генерации цепочки Project -> TaskList -> Task."""

    async def _create(test_user) -> Task:
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        project = Project(
            name='Test Project',
            user_id=test_user.id,
            status=ProjectStatus.IN_PROGRESS,
            deadline=future_datetime_mock,
            created_at=now_naive,
        )
        db_session.add(project)
        await db_session.flush()

        tasklist = TaskList(
            name='Test List',
            project_id=project.id,
            seq_number=1,
            status='Активный',
        )
        db_session.add(tasklist)
        await db_session.flush()

        task = Task(
            name='Test Task',
            tasklist_id=tasklist.id,
            status=TaskStatus.IN_PROGRESS,
            created_at=now_naive,
        )
        db_session.add(task)
        await db_session.commit()
        return task

    return _create


@pytest_asyncio.fixture
def create_custom_task_factory(db_session, future_datetime_mock):
    """Фабрика создания задачи с кастомными статусами, дедлайнами и стартом."""

    async def _create(
        test_user,
        status: TaskStatus = TaskStatus.IN_PROGRESS,
        deadline: datetime = None,
        start_at: datetime = None,
    ) -> Task:
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        project = Project(
            name='Test Project',
            user_id=test_user.id,
            status=ProjectStatus.IN_PROGRESS,
            deadline=future_datetime_mock,
            created_at=now_naive,
        )
        db_session.add(project)
        await db_session.flush()

        tasklist = TaskList(
            name='Test List',
            project_id=project.id,
            seq_number=1,
            status='Активный',
        )
        db_session.add(tasklist)
        await db_session.flush()

        task = Task(
            name='Test Task',
            tasklist_id=tasklist.id,
            status=status,
            priority=TaskPriority.MID,
            deadline=deadline,
            start_at=start_at,
            created_at=now_naive,
        )
        db_session.add(task)
        await db_session.commit()
        return task

    return _create


@pytest_asyncio.fixture
def create_attachment_factory(db_session):
    """Фабрика для генерации ORM-объектов вложений в СУБД."""

    async def _create(mime_type_str: str = 'JPEG') -> Attachment:
        class FakeEnum(str):
            @property
            def value(self):
                return self

            def __str__(self):
                return self

        attachment = Attachment(
            filename='test.jpg',
            size=1024,
            minio_name='test_minio',
            mime_type=FakeEnum(mime_type_str),
        )
        db_session.add(attachment)
        await db_session.commit()
        return attachment

    return _create


@pytest_asyncio.fixture
def create_test_reminder_factory(db_session):
    """Фабрика создания объектов напоминаний в тестовой СУБД."""

    async def _create(
        task_id: int,
        send_time: datetime,
        status: ReminderStatus = ReminderStatus.QUEUED,
    ) -> Reminder:
        reminder = Reminder(
            task_id=task_id,
            send_time=send_time,
            channel=ReminderChannel.EMAIL,
            status=status,
            was_read=False,
        )
        db_session.add(reminder)
        await db_session.commit()
        return reminder

    return _create


@pytest_asyncio.fixture
def create_test_tag_factory(db_session):
    """Фабрика для генерации ORM-объектов тегов в тестовой СУБД."""

    async def _create(user_id: int, name: str) -> Tag:
        tag = Tag(name=name, user_id=user_id)
        db_session.add(tag)
        await db_session.commit()
        return tag

    return _create
