import sys
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

# Выравнивание путей для бесшовного импорта модулей
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TASKS_APP_DIR = ROOT_DIR / 'tasks' / 'app'

if str(TASKS_APP_DIR) not in sys.path:
    sys.path.insert(0, str(TASKS_APP_DIR))

import core.redis as app_redis  # noqa: E402
import database.db as db_module  # noqa: E402
import services.users as users_service  # noqa: E402
from database.db import Base  # noqa: E402
from main import app  # noqa: E402
from models.enums import (  # noqa: E402
    ProjectStatus,
    ReminderChannel,
    ReminderStatus,
    TaskPriority,
    TaskStatus,
    Timezone,
    UserRole,
)
from models.taskflow import (  # noqa: E402
    Attachment,
    Project,
    Reminder,
    Tag,
    Task,
    TaskList,
)
from models.users import Token, User  # noqa: E402
from schemas.projects import ProjectCreate  # noqa: E402
from schemas.users import RegisterRequest  # noqa: E402
from services.auth import auth_service  # noqa: E402
from tests.infra_service import DockerSubprocessInfraService  # noqa: E402

# Синглтон инфраструктурного менеджера домена Tasks (Порт 5436)
tasks_infra = DockerSubprocessInfraService(
    container_name='tasks_db_test',
    env_file_path='./tests/tasks/.env.tasks.test',
    host_port=5436,
)


# Прямая инжекция пустых асинхронных функций-заглушек в синглтоны Redis
async def dummy_redis_call(*_args: Any, **_kwargs: Any) -> bool:
    """Бесшумная заглушка, заменяющая вызовы к Redis."""
    return True


async def dummy_redis_get(*_args: Any, **_kwargs: Any) -> None:
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

# =============================================================================
# 🐳 ZONE 1: РАБОТА С СИСТЕМНЫМИ ХУКАМИ И ЖИЗНЕННЫМ ЦИКЛОМ DOCKER
# =============================================================================


# pylint: disable=unused-argument
def pytest_sessionstart(session: pytest.Session) -> None:
    """Глобальный хук инициализации тестовой сессии.

    Разворачивает изолированный контейнер СУБД для тасок ДО начала
    сборки тестов и запуска асинхронных циклов.
    """
    tasks_infra.start_infra()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Глобальный хук завершения тестовой сессии.

    Обеспечивает очистку ресурсов хост-машины и удаление контейнера.
    """
    tasks_infra.stop_infra()


# =============================================================================
# 🗄️ ZONE 2: ИНИЦИАЛИЗАЦИЯ СУБД, ЖИЗНЕННЫЙ ЦИКЛ ТАБЛИЦ И СЕССИЙ
# =============================================================================


@pytest_asyncio.fixture(scope='session')
async def db_engine():
    """Инициализация асинхронного движка SQLAlchemy и генерация DDL."""
    engine = create_async_engine(tasks_infra.get_db_url())

    async with engine.begin() as connection:
        await connection.run_sync(partial(Base.metadata.create_all))

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(partial(Base.metadata.drop_all))
    await engine.dispose()


@pytest_asyncio.fixture(scope='session')
async def test_session_maker(db_engine):
    """Создание сессионной фабрики для генерации транзакций."""
    maker = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return maker


@pytest_asyncio.fixture(autouse=True)
async def mock_session_maker(test_session_maker):
    """Глобальный перехватчик фабрики сессий бизнес-логики приложения."""
    original_session_maker = db_module.async_session_maker
    db_module.async_session_maker = test_session_maker
    try:
        yield
    finally:
        db_module.async_session_maker = original_session_maker


@pytest_asyncio.fixture(autouse=True)
async def clean_database_tables(test_session_maker):
    """Принудительная каскадная очистка всех ORM-таблиц перед каждым тестом.

    Динамически извлекает имена существующих таблиц из метаданных Base,
    предотвращая ошибки UndefinedTableError при изменении схемы.
    """
    async with test_session_maker() as session:
        # 🧠 Динамически собираем имена всех зарегистрированных таблиц из ORM
        table_names = [table.name for table in Base.metadata.sorted_tables]

        if table_names:
            # Склеиваем имена через запятую для одной быстрой команды Postgres
            tables_str = ', '.join(f'"{name}"' for name in table_names)
            truncate_query = (
                f'TRUNCATE TABLE {tables_str} RESTART IDENTITY CASCADE;'
            )
            await session.execute(text(truncate_query))
            await session.commit()
    yield


@pytest_asyncio.fixture
async def db_session(test_session_maker):
    """Предоставление чистой асинхронной сессии для контекста тестов."""
    async with test_session_maker() as session:
        yield session


@pytest.fixture(scope='function')
def sync_db_session():
    """Синхронная сессия СУБД для тестирования Celery-задач Beat.

    Динамически адаптирует асинхронный DSN провайдера инфраструктуры
    под требования синхронного драйвера psycopg2.
    """
    async_url = tasks_infra.get_db_url()
    sync_url = async_url.replace('postgresql+asyncpg://', 'postgresql://')

    engine = create_engine(sync_url, pool_pre_ping=True)
    # 🔥 ИСПРАВЛЕНО: Имя переменной переведено в каноничный snake_case
    sync_session_local = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    session = sync_session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# =============================================================================
# 🧬 ZONE 3: МОКИРОВАНИЕ, МОНКИПАЙТЧИНГ И ПЕРЕХВАТ ПОВЕДЕНИЯ СУБД
# =============================================================================


@pytest.fixture
def force_commit_failure(monkeypatch: pytest.MonkeyPatch):
    """Точечно подменяет AsyncSession.commit на ошибку SQLAlchemyError."""

    def _activate() -> None:
        async def _fail_commit(_self) -> None:  # noqa: ANN001
            raise SQLAlchemyError('commit failed')

        monkeypatch.setattr(AsyncSession, 'commit', _fail_commit)

    return _activate

# =============================================================================
# 🌐 ZONE 4: ПРОФИЛИ ТЕСТОВЫХ ПОЛЬЗОВАТЕЛЕЙ И АВТОРИЗАЦИЯ (HTTPX CLIENT)
# =============================================================================

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
    async with AsyncClient(
        transport=transport, base_url='http://test'
    ) as ac:
        yield ac


# =============================================================================
# 🧬 ZONE 5: СЕТЕВЫЕ ЗАГЛУШКИ И СТОРОННИЕ СЕРВИСЫ
# =============================================================================

@pytest_asyncio.fixture(autouse=True)
async def clear_redis_cache():
    """Автоматически очищает Redis между тестами для изоляции кэша."""
    yield


@pytest.fixture(autouse=True)
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


@pytest.fixture
def mock_send_confirmation_email():
    """Имитирует отложенную задачу Celery по отправке подтверждения email.

    Подменяет реальный вызов фонового процесса отправки на тестовую
    заглушку для изоляции сетевых взаимодействий.
    """
    with patch('routers.auth.send_confirmation_email_task.delay') as mock:
        yield mock


@pytest.fixture
def mock_send_password_reset_email():
    """Имитирует отложенную задачу Celery по сбросу пароля пользователя.

    Подменяет реальный вызов фонового процесса отправки на тестовую
    заглушку для изоляции сетевых взаимодействий.
    """
    with patch('routers.auth.send_password_reset_email_task.delay') as mock:
        yield mock


# =============================================================================
# 🎭 ZONE 6: ЛЕГКОВЕСНЫЕ СХЕМЫ, ХЕЛПЕРЫ ДАТ И ИЕРАРХИИ ПУТЕЙ
# =============================================================================

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


@pytest.fixture
def mock_user_factory(mocker):
    """Фабрика для генерации легковесных мок-объектов пользователей."""
    def _create(user_id: int = 123) -> mocker.Mock:
        user = mocker.Mock()
        user.id = user_id
        return user
    return _create


@pytest.fixture
def mock_reminder_factory(mocker):
    """Фабрика для генерации легковесных мок-объектов напоминаний."""
    def _create(reminder_id: int = 777) -> mocker.Mock:
        reminder = mocker.Mock()
        reminder.id = reminder_id
        return reminder
    return _create


@pytest.fixture
def mock_objects_factory(mocker):
    """Фабрика для генерации вложенных мок-контекстов Канбана и тегов."""
    def _create(
        user_id: int = 123,
        project_id: int = 10,
        tasklist_id: int = 777,
        task_id: int = 456,
        subtask_id: int = 123,
        tag_id: int = 777,
        user_tz: str = 'Europe/Moscow',
    ) -> mocker.Mock:
        obj = mocker.Mock()
        obj.project.id = project_id
        obj.project.user_id = user_id
        obj.project.user.timezone.value = user_tz
        obj.tasklist.id = tasklist_id
        obj.task.id = task_id
        obj.subtask.id = subtask_id
        obj.tag.id = tag_id
        return obj
    return _create


@pytest.fixture
def mock_crud_factory(mocker):
    """Фабрика для генерации асинхронных заглушек методов базового CRUD."""

    def _mock_method(
        router_path: str,
        method_name: str = 'add',
        return_value: Any = None,
        side_effect: Any = None,
    ) -> mocker.AsyncMock:
        # Если return_value не передан, по дефолту для .add() создаем Mock(id=1)
        if return_value is None and method_name == 'add':
            return_value = mocker.Mock(id=1)

        mock_func = mocker.patch(
            f'routers.{router_path}.service.{method_name}',
            new_callable=mocker.AsyncMock,
        )

        if side_effect:
            mock_func.side_effect = side_effect
        else:
            mock_func.return_value = return_value

        return mock_func
    return _mock_method


# =============================================================================
# 🏗️ ZONE 7: ПРОМЫШЛЕННЫЕ ORM-ФАБРИКИ (FIXTURE FACTORIES) СУБД ТАСОК
# =============================================================================

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
    """Фабрика для generation ORM-объектов списков задач в СУБД."""

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
    """Фабрика создания задачи с кастомными статусами и дедлайнами."""

    async def _create(
        test_user,
        status: TaskStatus = TaskStatus.IN_PROGRESS,
        deadline: datetime | None = None,
        start_at: datetime | None = None,
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

