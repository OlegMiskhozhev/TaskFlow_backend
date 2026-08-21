import sys
from collections.abc import AsyncGenerator, Callable
from datetime import date
from functools import partial
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Корректировка путей для бесшовного импорта модулей из корня проекта
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
FLOW_APP_DIR = ROOT_DIR / 'flow' / 'app'

if str(FLOW_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLOW_APP_DIR))

import database.db as db_module  # noqa: E402
from core.dependency import get_current_user_id  # noqa: E402
from database.db import Base  # noqa: E402
from models.flow import Note  # noqa: E402
from routers.core import core_router  # noqa: E402
from tests.infra_service import DockerSubprocessInfraService  # noqa: E402

# Синглтон инфраструктурного менеджера домена Flow
flow_infra = DockerSubprocessInfraService(
    container_name='flow_db_test',
    env_file_path='./tests/flow/.env.flow.test',
    host_port=5435,
)


# =============================================================================
# 🐳 ZONE 1: РАБОТА С СИСТЕМНЫМИ ХУКАМИ И ЖИЗНЕННЫМ ЦИКЛОМ DOCKER
# =============================================================================


def pytest_sessionstart(
        session: pytest.Session  # noqa: ARG001
) -> None:
    """Глобальный хук инициализации тестовой сессии.

    Гарантированно разворачивает изолированный контейнер СУБД ДО
    начала сборки тестов и запуска асинхронных циклов.
    """
    flow_infra.start_infra()


def pytest_sessionfinish(
        session: pytest.Session,  # noqa: ARG001
        exitstatus: int  # noqa: ARG001
) -> None:
    """Глобальный хук завершения тестовой сессии.

    Обеспечивает гарантированную очистку ресурсов хост-машины и
    удаление тестового контейнера после выполнения всех проверок.
    """
    flow_infra.stop_infra()



# =============================================================================
# 🗄️ ZONE 2: ИНИЦИАЛИЗАЦИЯ СУБД, ЖИЗНЕННЫЙ ЦИКЛ ТАБЛИЦ И СЕССИЙ
# =============================================================================


@pytest_asyncio.fixture(scope='session')
async def db_engine():
    """Инициализация асинхронного движка SQLAlchemy и генерация DDL."""
    engine = create_async_engine(flow_infra.get_db_url())

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
    """Принудительная очистка таблиц перед каждым тест-кейсом.

    Обеспечивает стерильность базы данных между тестами, предотвращая
    эффект накопления данных прошлых сессий выполнения.
    """
    async with test_session_maker() as session:
        await session.execute(text('DELETE FROM notes;'))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def async_session_no_transaction(test_session_maker):
    """Предоставление чистой асинхронной сессии для фабрик тестов."""
    async with test_session_maker() as session:
        yield session


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
# 🌐 ZONE 4: ИНИЦИАЛИЗАЦИЯ FASTAPI ПРИЛОЖЕНИЯ И HTTP-КЛИЕНТОВ (HTTPX)
# =============================================================================


def _flow_app_with_user_resolver(get_user_id: Callable[[], int]) -> FastAPI:
    """Фабрика создания тестового инстанса приложения с подменой юзера."""
    application = FastAPI()
    application.include_router(core_router)
    application.dependency_overrides[get_current_user_id] = get_user_id
    return application


@pytest_asyncio.fixture
async def app():
    """Фикстура изолированного инстанса FastAPI с дефолтным юзером."""
    application = _flow_app_with_user_resolver(lambda: 1)
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_client(app: FastAPI):
    """Асинхронный HTTP-клиент для авторизованных интеграционных тестов."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url='http://testserver'
    ) as client:
        yield client


@pytest_asyncio.fixture
async def unauthorized_test_client() -> AsyncGenerator[AsyncClient, None]:
    """Асинхронный HTTP-клиент для эмуляции неавторизованных запросов."""

    def _raise_unauthorized() -> int:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired access token',
        )

    application = _flow_app_with_user_resolver(_raise_unauthorized)
    transport = ASGITransport(app=application)

    async with AsyncClient(
        transport=transport, base_url='http://testserver'
    ) as client:
        yield client

    # 🚀 ИСПРАВЛЕНО: Чистим оверрайды напрямую без лишнего cast
    application.dependency_overrides.clear()


# =============================================================================
# 🎭 ZONE 5: ДАННЫЕ, ДЕФОЛТНЫЕ СТАТИЧЕСКИЕ СУЩНОСТИ И ТЕСТОВЫЕ ФАБРИКИ
# =============================================================================


@pytest.fixture
def notes_api_prefix() -> str:
    """Базовый префикс роутера заметок."""
    return '/notes'


@pytest.fixture
def own_user_id() -> int:
    """Идентификатор текущего владельца сущностей."""
    return 1


@pytest.fixture
def foreign_user_id() -> int:
    """Идентификатор стороннего пользователя (проверка изоляции)."""
    return 2


@pytest.fixture
def auth_token() -> HTTPAuthorizationCredentials:
    """Шаблон валидных метаданных авторизации."""
    return HTTPAuthorizationCredentials(
        scheme='Bearer',
        credentials='test-access-token',
    )


@pytest_asyncio.fixture
async def note_factory(async_session_no_transaction: AsyncSession):
    """Фабрика для быстрой генерации сущностей Note в БД."""

    async def _create_note(
        *,
        user_id: int,
        content: str,
        note_date: date,
        is_completed: bool = False,
    ) -> Note:
        note = Note(
            user_id=user_id,
            content=content,
            note_date=note_date,
            is_completed=is_completed,
        )
        async_session_no_transaction.add(note)
        await async_session_no_transaction.commit()
        await async_session_no_transaction.refresh(note)
        return note

    return _create_note
