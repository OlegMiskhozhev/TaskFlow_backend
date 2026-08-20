# tests/tasks/unit/test_users_routes_unit.py
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

    async def test_avatar_info_calls_cache(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: извлечение ссылки на аватар из кэша профиля."""
        mock_cache = mocker.patch(
            'routers.users.get_cached_user_detail',
            new_callable=mocker.AsyncMock,
        )
        mock_cache.return_value = {'avatar_url': 'https://s3.local'}
        mock_user = mock_user_factory(user_id=1)

        result = await avatar_info(user=mock_user)

        assert result['avatar_url'] == 'https://s3.local'
        mock_cache.assert_called_once_with(mock_user)

    async def test_set_avatar_calls_update_and_invalidates_cache(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: установка аватара и атомарное затирание кэша."""
        mock_user = mock_user_factory(user_id=42)
        mock_file = mocker.Mock()

        mock_update = mocker.patch(
            'routers.users.update_avatar',
            new_callable=mocker.AsyncMock,
        )
        mock_cache = mocker.patch(
            'routers.users.redis_cache',
            new_callable=mocker.AsyncMock,
        )

        response = await set_avatar(user=mock_user, file=mock_file)

        assert response.status_code == status.HTTP_201_CREATED
        mock_update.assert_called_once_with(mock_user, mock_file)
        mock_cache.delete.assert_called_once_with('user:42:profile')


@pytest.mark.asyncio
class TestUserProfileRoutesUnit:
    """Юнит-тесты для роутеров извлечения и изменения профиля."""

    async def test_get_user_profile_calls_cache(
        self, mock_user_factory, mocker
    ) -> None:
        """Тест: получение полной структуры профиля из Redis."""
        mock_cache = mocker.patch(
            'routers.users.get_cached_user_detail',
            new_callable=mocker.AsyncMock,
        )
        mock_cache.return_value = {'id': 1, 'username': 'test'}
        mock_user = mock_user_factory()

        result = await get_user_profile(user=mock_user)

        assert result == {'id': 1, 'username': 'test'}
        mock_cache.assert_called_once_with(mock_user)

    async def test_update_user_profile_success(
        self, mock_user_factory, mock_crud_factory, mocker
    ) -> None:
        """Тест: успешное изменение полей профиля и сброс кэша."""
        mock_user = mock_user_factory(user_id=10)
        mock_updated_user = mocker.Mock()

        mock_update = mock_crud_factory(
            router_path='users',
            method_name='update',
            return_value=mock_updated_user,
        )
        mock_detail = mocker.patch(
            'routers.users.get_cached_user_detail',
            new_callable=mocker.AsyncMock,
        )
        mock_cache = mocker.patch(
            'routers.users.redis_cache',
            new_callable=mocker.AsyncMock,
        )

        mock_detail.return_value = {'id': 10, 'username': 'new_name'}
        user_data = UserUpdate(username='new_name')

        result = await update_user_profile(
            user_data=user_data, current_user=mock_user
        )

        assert result['username'] == 'new_name'
        mock_cache.delete.assert_called_once_with('user:10:profile')

        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs['model'] == User
        assert call_kwargs['values']['username'] == 'new_name'
        assert call_kwargs['values']['id'] == 10

    async def test_update_user_profile_integrity_error_409(
        self, mock_user_factory, mock_crud_factory
    ) -> None:
        """Тест: занятое имя пользователя корректно возвращает 409."""
        # Используем CRUD-фабрику с передачей Exception() для PyCharm
        mock_update = mock_crud_factory(
            router_path='users',
            method_name='update',
            side_effect=IntegrityError('Duplicate', {}, Exception()),
        )
        mock_user = mock_user_factory(user_id=10)
        user_data = UserUpdate(username='taken_name')

        with pytest.raises(HTTPException) as exc:
            await update_user_profile(
                user_data=user_data, current_user=mock_user
            )

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert exc.value.detail.get('msg') == (
            'Имя пользователя уже занято, попробуйте использовать другое.'
        )
        mock_update.assert_called_once()


@pytest.mark.asyncio
class TestGetUserIdUnit:
    """Юнит-тесты утилитарного роутера получения ID."""

    async def test_get_user_id_returns_correct_id(
        self, mock_user_factory
    ) -> None:
        """Тест: извлечение id текущего авторизованного пользователя."""
        mock_user = mock_user_factory(user_id=888)
        result = await get_user_id(user=mock_user)

        assert isinstance(result, UserId)
        assert result.id == 888
