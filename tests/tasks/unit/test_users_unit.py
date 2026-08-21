import json
from datetime import UTC, datetime

import pytest

from models.enums import ProjectStatus, Timezone
from models.taskflow import Project
from schemas.users import UserDetail
from services.users import get_cached_user_detail, get_user_detail


@pytest.mark.asyncio
class TestGetUserDetailUnit:
    """Юнит-тесты базового метода формирования профиля get_user_detail."""

    async def test_get_user_detail_success_no_projects(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: успешное извлечение профиля без проектов и аватара."""
        mocker.patch(
            'services.users.client',
            new_callable=mocker.AsyncMock,
        )
        mock_user = mock_user_factory(user_id=1)
        mock_user.email = 'test1@test.com'
        mock_user.username = 'user1'
        mock_user.projects = []
        mock_user.timezone = Timezone.UTC
        mock_user.avatar = None
        mock_user.avatar_url = None

        result = await get_user_detail(mock_user)

        assert isinstance(result, UserDetail)
        assert result.id == 1
        assert result.email == 'test1@test.com'
        assert result.avatar_url is None
        assert len(result.projects) == 0

    async def test_get_user_detail_with_avatar(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: вычисление внешней S3-ссылки по связи avatar в ОЗУ."""
        mock_client = mocker.patch(
            'services.users.client',
            new_callable=mocker.AsyncMock,
        )
        mock_client.get_url.return_value = 'https://s3.local'

        mock_avatar = mocker.Mock()
        mock_avatar.minio_name = 'uuid-123'
        mock_avatar.mime_type = 'png'

        mock_user = mock_user_factory(user_id=1)
        mock_user.username = 'user1'
        mock_user.email = 'test1@test.com'
        mock_user.timezone = Timezone.UTC
        mock_user.avatar = mock_avatar
        mock_user.avatar_url = 'https://s3.local'
        mock_user.projects = []

        result = await get_user_detail(mock_user)

        assert result.avatar_url == 'https://s3.local'
        mock_client.get_url.assert_called_once_with('uuid-123.png')

    async def test_get_user_detail_filter_archive_projects(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: фильтрация архивных проектов из списка."""
        mocker.patch(
            'services.users.client',
            new_callable=mocker.AsyncMock,
        )
        project_active = mocker.Mock(status=ProjectStatus.IN_PROGRESS, id=10)
        project_active.name = 'Active Project'
        project_active.__class__ = Project
        project_active.description = None
        project_active.created_at = datetime.now(UTC)

        project_archive = mocker.Mock(status=ProjectStatus.ARCHIVE, id=20)
        project_archive.name = 'Archive Project'
        project_archive.__class__ = Project
        project_archive.description = None
        project_archive.created_at = datetime.now(UTC)

        mock_user = mock_user_factory(user_id=1)
        mock_user.username = 'user1'
        mock_user.email = 'test1@test.com'
        mock_user.timezone = Timezone.UTC
        mock_user.avatar = None
        mock_user.avatar_url = None
        mock_user.projects = [project_active, project_archive]

        result = await get_user_detail(mock_user)

        assert len(result.projects) == 1
        assert result.projects[0].name == 'Active Project'


@pytest.mark.asyncio
class TestGetCachedUserDetailUnit:
    """Юнит-тесты диспетчера кэширования профилей get_cached_user_detail."""

    async def test_get_cached_user_detail_cache_hit(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: мгновенный возврат JSON из Redis без вызова СУБД."""
        mock_redis = mocker.patch(
            'services.users.redis_cache',
            new_callable=mocker.AsyncMock,
        )
        cached_profile = {'id': 5, 'username': 'cached_user'}
        mock_redis.get.return_value = json.dumps(cached_profile)

        mock_user = mock_user_factory(user_id=5)

        result = await get_cached_user_detail(mock_user)

        assert result == cached_profile
        mock_redis.get.assert_called_once_with('user:5:profile')

    async def test_get_cached_user_detail_cache_miss_writes_cache(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: промах кэша вызывает генерацию и запись в Redis на 1 час."""
        mock_redis = mocker.patch(
            'services.users.redis_cache',
            new_callable=mocker.AsyncMock,
        )
        mock_get_detail = mocker.patch(
            'services.users.get_user_detail',
            new_callable=mocker.AsyncMock,
        )
        mock_redis.get.return_value = None

        mock_detail_dto = mocker.Mock()
        mock_detail_dto.model_dump.return_value = {'id': 9, 'username': 'db'}
        mock_get_detail.return_value = mock_detail_dto

        mock_user = mock_user_factory(user_id=9)

        result = await get_cached_user_detail(mock_user)

        assert result == {'id': 9, 'username': 'db'}
        mock_get_detail.assert_called_once_with(mock_user)
        mock_redis.set.assert_called_once_with(
            'user:9:profile', json.dumps({'id': 9, 'username': 'db'}), ex=3600
        )
