from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from models.users import User
from routers.users import (
    avatar_info,
    get_user_id,
    get_user_profile,
    set_avatar,
    update_user_profile,
)
from schemas.users import UserId, UserUpdate


@pytest.mark.asyncio
class TestAvatarRoutesUnit:
    """Юнит-тесты для роутеров управления аватаром пользователя."""

    @patch('routers.users.get_cached_user_detail', new_callable=AsyncMock)
    async def test_avatar_info_calls_cache(self, mock_cache):
        """Тест: извлечение ссылки на аватар из кэша профиля."""
        mock_cache.return_value = {'avatar_url': 'https://s3.local'}
        mock_user = Mock(id=1)

        result = await avatar_info(user=mock_user)

        assert result['avatar_url'] == 'https://s3.local'
        mock_cache.assert_called_once_with(mock_user)

    @patch('routers.users.update_avatar', new_callable=AsyncMock)
    @patch('routers.users.redis_cache', new_callable=AsyncMock)
    async def test_set_avatar_calls_update_and_invalidates_cache(
        self, mock_cache, mock_update
    ):
        """Тест: установка аватара и атомарное затирание кэша."""
        mock_user = Mock(id=42)
        mock_file = Mock()

        response = await set_avatar(user=mock_user, file=mock_file)

        assert response.status_code == status.HTTP_201_CREATED
        mock_update.assert_called_once_with(mock_user, mock_file)
        mock_cache.delete.assert_called_once_with('user:42:profile')


@pytest.mark.asyncio
class TestUserProfileRoutesUnit:
    """Юнит-тесты для роутеров извлечения и изменения профиля."""

    @patch('routers.users.get_cached_user_detail', new_callable=AsyncMock)
    async def test_get_user_profile_calls_cache(self, mock_cache):
        """Тест: получение полной структуры профиля из Redis."""
        mock_cache.return_value = {'id': 1, 'username': 'test'}
        mock_user = Mock()

        result = await get_user_profile(user=mock_user)

        assert result == {'id': 1, 'username': 'test'}
        mock_cache.assert_called_once_with(mock_user)

    @patch('routers.users.service.update', new_callable=AsyncMock)
    @patch('routers.users.get_cached_user_detail', new_callable=AsyncMock)
    @patch('routers.users.redis_cache', new_callable=AsyncMock)
    async def test_update_user_profile_success(
        self, mock_cache, mock_detail, mock_update
    ):
        """Тест: успешное изменение полей профиля и сброс кэша."""
        mock_user = Mock(id=10)
        mock_updated_user = Mock()
        mock_update.return_value = mock_updated_user
        mock_detail.return_value = {'id': 10, 'username': 'new_name'}

        user_data = UserUpdate(username='new_name')

        result = await update_user_profile(
            user_data=user_data, current_user=mock_user
        )

        assert result['username'] == 'new_name'
        mock_cache.delete.assert_called_once_with('user:10:profile')

        # Исправлено: сверяем параметры строго через именованные kwargs
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs['model'] == User
        assert call_kwargs['values']['username'] == 'new_name'
        assert call_kwargs['values']['id'] == 10

    @patch('routers.users.service.update', new_callable=AsyncMock)
    async def test_update_user_profile_integrity_error_409(self, mock_update):
        """Тест: занятое имя пользователя корректно возвращает 409."""
        mock_update.side_effect = IntegrityError('Duplicate', {}, None)
        mock_user = Mock(id=10)
        user_data = UserUpdate(username='taken_name')

        with pytest.raises(HTTPException) as exc:
            await update_user_profile(
                user_data=user_data, current_user=mock_user
            )

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert exc.value.detail['msg'] == (
            'Имя пользователя уже занято, попробуйте использовать другое.'
        )


@pytest.mark.asyncio
class TestGetUserIdUnit:
    """Юнит-тесты утилитарного роутера получения ID."""

    async def test_get_user_id_returns_correct_id(self):
        """Тест: извлечение id текущего авторизованного пользователя."""
        mock_user = Mock(id=888)
        result = await get_user_id(user=mock_user)

        assert isinstance(result, UserId)
        assert result.id == 888
