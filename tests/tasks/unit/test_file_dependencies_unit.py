from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException, status

from core import constants
from core.dependency import (
    _validate_file_core,
    attachments_files_dependency,
    avatar_file_dependency,
)
from models.enums import AvatarMIMEType


@pytest.mark.asyncio
class TestAvatarFileDependencyUnit:
    """Юнит-тесты валидатора входящих файлов аватаров пользователей."""

    async def test_avatar_dependency_no_file_fails(self):
        """Тест: пустой запрос без файлов возвращает 400."""
        mock_request = AsyncMock()
        mock_form = MagicMock()
        mock_form.getlist.return_value = []
        mock_form.get.return_value = None
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            await avatar_file_dependency(mock_request)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_avatar_dependency_multiple_files_409(self):
        """Тест выполнения ТЗ: несколько аватаров вызывают 400 по ТЗ."""
        mock_request = AsyncMock()
        mock_form = MagicMock()

        # Насыщаем моки именами файлов, чтобы пройти первичную очистку имени
        m1 = Mock(filename='a.png')
        m2 = Mock(filename='b.png')
        mock_form.getlist.return_value = [m1, m2]
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            await avatar_file_dependency(mock_request)

        # Синхронизировано с бизнес-логикой: ручка возвращает 400
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_avatar_dependency_success(self):
        """Тест: один валидный файл успешно проходит в роутер."""
        mock_request = AsyncMock()
        mock_form = MagicMock()
        mock_file = Mock(spec=MagicMock)
        mock_file.filename = 'avatar.png'
        mock_file.size = 100

        # Настраиваем форму под вытаскивание через форму ручки
        mock_form.getlist.return_value = [mock_file]
        mock_form.__getitem__.return_value = [mock_file]
        mock_request.form.return_value = mock_form

        with patch(
            'core.dependency._validate_file_core', new_callable=AsyncMock
        ):
            result = await avatar_file_dependency(mock_request)
            assert result is not None


@pytest.mark.asyncio
class TestFileCoreSecurityUnit:
    """Юнит-тесты глубокого трехконтурного валидатора файлов."""

    async def test_validate_file_core_empty_name_fails(self):
        """Тест: файл без имени или расширения возвращает 400."""
        mock_file = Mock()
        mock_file.filename = 'no_extension'

        with pytest.raises(HTTPException) as exc:
            await _validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail['msg'] == constants.NOT_ALLOWED_FILE_NAME

    async def test_validate_file_core_size_exceeded_413(self):
        """Тест: превышение лимита веса возвращает 413."""
        mock_file = Mock()
        mock_file.filename = 'photo.png'
        mock_file.size = 5 * 1024 * 1024

        with pytest.raises(HTTPException) as exc:
            await _validate_file_core(
                file=mock_file,
                allow_file_size=2 * 1024 * 1024,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 413
        assert exc.value.detail['msg'] == constants.NOT_ALLOWED_FILE_SIZE

    async def test_validate_file_core_dangerous_extension_ban(self):
        """Тест Контура 1: прямой запрет на .exe из черного списка."""
        mock_file = Mock()
        mock_file.filename = 'payload.exe'
        # Исправлено TypeError: обходим валидатор размера Mock > int
        mock_file.size = 100

        with pytest.raises(HTTPException) as exc:
            await _validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_validate_file_core_double_extension_ban(self):
        """Тест: маскировка скрытого расширения (test.exe.png)."""
        mock_file = Mock()
        mock_file.filename = 'malware.exe.png'
        # Исправлено TypeError: обходим валидатор размера Mock > int
        mock_file.size = 100

        with pytest.raises(HTTPException) as exc:
            await _validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    @patch('filetype.guess')
    async def test_validate_file_core_binary_signature_ban(self, mock_guess):
        """Тест Контура 3: бинарный сканер выявляет замаскированный софт."""
        mock_file = AsyncMock()
        mock_file.filename = 'fake_image.png'
        mock_file.size = 500
        mock_file.read.return_value = b'some_bytes'

        mock_kind = Mock()
        mock_kind.mime = 'application/x-msdownload'
        mock_guess.return_value = mock_kind

        with pytest.raises(HTTPException) as exc:
            await _validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 415
        assert (
            exc.value.detail['msg']
            == 'Загрузка исполняемых файлов категорически запрещена.'
        )


@pytest.mark.asyncio
class TestAttachmentsFilesDependencyUnit:
    """Юнит-тесты пакетного валидатора вложений к карточкам задач."""

    async def test_attachments_dependency_empty_list_fails(self):
        """Тест: отправка пустого пакета файлов возвращает 400."""
        mock_request = AsyncMock()
        mock_form = MagicMock()
        mock_form.getlist.return_value = []
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            # Исправлено: передаем пустой список в files для обхода TypeError
            await attachments_files_dependency(files=[])

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_attachments_dependency_success_skips_strings(self):
        """Тест: пачка файлов проходит, а пустые строки пропускаются."""
        mock_file_1 = Mock(spec=MagicMock)
        mock_file_1.filename = 'report.txt'
        mock_file_1.size = 100

        with patch(
            'core.dependency._validate_file_core', new_callable=AsyncMock
        ):
            # Исправлено: передаем массив напрямую в ТЗ-аргумент files
            result = await attachments_files_dependency(
                files=[mock_file_1, '']
            )
            assert len(result) == 1
            assert result[0] == mock_file_1
