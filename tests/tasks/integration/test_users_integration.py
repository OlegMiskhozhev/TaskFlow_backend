from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models.users import Avatar, User
from services.users import (
    get_user_by_email,
    get_user_by_token,
    get_user_detail,
    update_avatar,
)


@pytest.mark.asyncio
class TestUsersServiceIntegration:
    """Интеграционные тесты сервисного слоя управления пользователями."""

    async def test_get_user_by_email_integration(
        self, db_session, create_test_user_factory
    ):
        """Проверяет атомарный поиск пользователя в СУБД по его email."""
        created_user = await create_test_user_factory(
            email='findme@test.com', username='findme'
        )

        user = await get_user_by_email('findme@test.com')
        assert user is not None
        assert user.email == 'findme@test.com'
        assert user.id == created_user.id

        not_found = await get_user_by_email('nonexistent@test.com')
        assert not_found is None

    async def test_get_user_by_token_integration(
        self, db_session, create_test_user_factory, create_test_token_factory
    ):
        """Проверяет извлечение активного пользователя по JWT сессии."""
        user = await create_test_user_factory(
            email='token_user@test.com', username='tokenuser'
        )
        token_record = await create_test_token_factory(
            user_id=user.id, access_token='test_access_token', is_active=True
        )

        db_user = await get_user_by_token('test_access_token')
        assert db_user is not None
        assert db_user.id == user.id
        assert db_user.email == 'token_user@test.com'

        token_record.is_active = False
        await db_session.commit()
        db_session.expire_all()

        user_inactive = await get_user_by_token('test_access_token')
        assert user_inactive is None

    async def test_get_user_detail_integration(
        self, db_session, create_test_user_factory
    ):
        """Проверяет сборку детальной структуры профиля по ORM связям."""
        user_base = await create_test_user_factory(
            email='detail_test@test.com', username='detailuser'
        )

        # Жадно подгружаем проекты для Pydantic, предотвращая MissingGreenlet
        stmt = (
            select(User)
            .where(User.id == user_base.id)
            .options(selectinload(User.projects))
        )
        res = await db_session.execute(stmt)
        user_orm = res.scalar_one()

        db_session.expunge_all()

        # Вызываем метод профиля (MinIO клиент изолирован фикстурой)
        result = await get_user_detail(user_orm)

        assert result.email == 'detail_test@test.com'
        assert result.username == 'detailuser'
        # Исправлено: у пользователя без аватара ссылка должна быть None
        assert result.avatar_url is None

    @patch('services.users.uuid4')
    @patch('services.users.client.upload_file', new_callable=AsyncMock)
    async def test_update_avatar_integration(
        self, mock_upload, mock_uuid, db_session, create_test_user_factory
    ):
        """Проверяет создание нового аватара для пользователя."""
        user_orm = await create_test_user_factory(
            email='update_avatar@test.com', username='updateavatar'
        )
        user_id = user_orm.id
        mock_uuid.return_value = 'acefbd9e-5f17-4422-baea-6fd29c84f74c'

        mock_file = AsyncMock()
        mock_file.filename = 'new_avatar.jpg'
        mock_file.size = 1024
        mock_file.file = Mock()

        # Отсоединяем объект от тестовой сессии перед входом в @connection
        db_session.expunge(user_orm)

        # Запускаем транзакционный метод обновления
        await update_avatar(user_orm, mock_file)

        # Вычищаем кэш ОЗУ тестовой сессии через close() вместо expire_all()
        await db_session.close()

        # Исправлено MissingGreenlet: используем изолированную переменную ID
        stmt = select(Avatar).where(Avatar.user_id == user_id)
        result = await db_session.execute(stmt)
        avatar = result.scalar_one_or_none()

        assert avatar is not None
        assert avatar.filename == 'new_avatar.jpg'
        assert avatar.mime_type == 'jpg'
        assert avatar.user_id == user_id

    @patch('services.users.uuid4')
    @patch('services.users.client.upload_file', new_callable=AsyncMock)
    async def test_update_avatar_existing_avatar_integration(
        self, mock_upload, mock_uuid, db_session, create_test_user_factory
    ):
        """Проверяет обновление полей существующего аватара."""
        user_orm = await create_test_user_factory(
            email='existing_avatar@test.com', username='existinguser'
        )
        user_id = user_orm.id

        mock_uuid.return_value = 'old-uuid-111'
        mock_file_first = AsyncMock()
        mock_file_first.filename = 'old_avatar.jpg'
        mock_file_first.size = 1024
        mock_file_first.file = Mock()

        await update_avatar(user_orm, mock_file_first)

        # Переписываем аватар на новый файл
        mock_uuid.return_value = 'new-uuid-222'
        mock_file_new = AsyncMock()
        mock_file_new.filename = 'new_avatar.png'
        mock_file_new.size = 2048
        mock_file_new.file = Mock()

        await update_avatar(user_orm, mock_file_new)

        await db_session.close()

        stmt = select(Avatar).where(Avatar.user_id == user_id)
        result = await db_session.execute(stmt)
        avatar = result.scalar_one_or_none()

        assert avatar is not None
        assert avatar.filename == 'new_avatar.png'
        assert avatar.minio_name == 'new-uuid-222'
        assert avatar.mime_type == 'png'

    @patch('services.users.uuid4')
    @patch('services.users.client.upload_file', new_callable=AsyncMock)
    async def test_update_avatar_upload_called_properly(
        self, mock_upload, mock_uuid, db_session, create_test_user_factory
    ):
        """Проверяет передачу аргументов в S3 клиент при выгрузке."""
        user_orm = await create_test_user_factory(
            email='upload_test@test.com', username='uploaduser'
        )
        mock_uuid.return_value = 'test-uuid-333'

        mock_file = AsyncMock()
        mock_file.filename = 'test.jpg'
        mock_file.size = 1024
        mock_file.file = Mock()

        await update_avatar(user_orm, mock_file)

        mock_upload.assert_called_once_with(
            'test-uuid-333.jpg', mock_file.file, 1024
        )
