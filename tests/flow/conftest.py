import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
FLOW_APP_DIR = ROOT_DIR / 'flow' / 'app'

if str(FLOW_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLOW_APP_DIR))

import database.db as db_module  # noqa: E402
from core.dependency import get_current_user_id  # noqa: E402
from database.db import Base  # noqa: E402
from models.flow import Note  # noqa: E402
from routers.core import core_router  # noqa: E402


def _flow_app_with_user_resolver(get_user_id: Callable[[], int]) -> FastAPI:
    application = FastAPI()
    application.include_router(core_router)
    overrides = cast(
        dict[Callable[..., Any], Callable[..., Any]],
        application.dependency_overrides,  # type: ignore[attr-defined]
    )
    overrides[get_current_user_id] = get_user_id
    return application


@pytest_asyncio.fixture
async def manage_db():
    yield


@pytest_asyncio.fixture
async def db_engine(manage_db):
    engine = create_async_engine(db_module.settings.db_settings.db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_maker(db_engine):
    maker = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return maker


@pytest.fixture
def force_commit_failure(monkeypatch: pytest.MonkeyPatch):
    """Точечно подменяет AsyncSession.commit на SQLAlchemyError."""

    def _activate() -> None:
        async def _fail_commit(_self) -> None:  # noqa: ANN001
            raise SQLAlchemyError('commit failed')

        monkeypatch.setattr(AsyncSession, 'commit', _fail_commit)

    return _activate


@pytest_asyncio.fixture(autouse=True)
async def mock_session_maker(test_session_maker):
    original_session_maker = db_module.async_session_maker
    db_module.async_session_maker = test_session_maker
    try:
        yield
    finally:
        db_module.async_session_maker = original_session_maker


@pytest_asyncio.fixture
async def async_session_no_transaction(test_session_maker):
    async with test_session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    application = _flow_app_with_user_resolver(lambda: 1)
    overrides = cast(
        dict[Callable[..., Any], Callable[..., Any]],
        application.dependency_overrides,  # type: ignore[attr-defined]
    )
    yield application
    overrides.clear()


@pytest_asyncio.fixture
async def test_client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url='http://testserver'
    ) as client:
        yield client


@pytest_asyncio.fixture
async def unauthorized_test_client() -> AsyncClient:
    def _raise_unauthorized() -> int:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired access token',
        )

    application = _flow_app_with_user_resolver(_raise_unauthorized)
    overrides = cast(
        dict[Callable[..., Any], Callable[..., Any]],
        application.dependency_overrides,  # type: ignore[attr-defined]
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport, base_url='http://testserver'
    ) as client:
        yield client
    overrides.clear()


@pytest.fixture
def notes_api_prefix() -> str:
    return '/notes'


@pytest.fixture
def own_user_id() -> int:
    return 1


@pytest.fixture
def foreign_user_id() -> int:
    return 2


@pytest.fixture
def auth_token() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(
        scheme='Bearer',
        credentials='test-access-token',
    )


@pytest_asyncio.fixture
async def note_factory(async_session_no_transaction: AsyncSession):
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
