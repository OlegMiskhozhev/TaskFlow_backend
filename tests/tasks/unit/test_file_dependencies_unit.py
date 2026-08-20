import pytest
from fastapi import HTTPException, status

from core import constants, dependency
from core.dependency import (
    attachments_files_dependency,
    avatar_file_dependency,
)
from models.enums import AvatarMIMEType


@pytest.mark.asyncio
class TestAvatarFileDependencyUnit:
    """Юнит-тесты валидатора входящих файлов аватаров пользователей."""

    async def test_avatar_dependency_no_file_fails(self, mocker) -> None:
        """Тест: пустой запрос без файлов возвращает 400."""
        mock_request = mocker.AsyncMock()
        mock_form = mocker.MagicMock()
        mock_form.getlist.return_value = []
        mock_form.get.return_value = None
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            await avatar_file_dependency(mock_request)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_avatar_dependency_multiple_files_409(self, mocker) -> None:
        """Тест выполнения ТЗ: несколько аватаров вызывают 400 по ТЗ."""
        mock_request = mocker.AsyncMock()
        mock_form = mocker.MagicMock()

        m1 = mocker.Mock(filename='a.png')
        m2 = mocker.Mock(filename='b.png')
        mock_form.getlist.return_value = [m1, m2]
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            await avatar_file_dependency(mock_request)

        # Синхронизировано с бизнес-логикой: ручка возвращает 400
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_avatar_dependency_success(self, mocker) -> None:
        """Тест: один валидный файл успешно проходит в роутер."""
        mock_request = mocker.AsyncMock()
        mock_form = mocker.MagicMock()
        mock_file = mocker.Mock(spec=mocker.MagicMock)
        mock_file.filename = 'avatar.png'
        mock_file.size = 100

        # Настраиваем форму под вытаскивание через форму ручки
        mock_form.getlist.return_value = [mock_file]
        mock_form.__getitem__.return_value = [mock_file]
        mock_request.form.return_value = mock_form

        mocker.patch(
            'core.dependency._validate_file_core',
            new_callable=mocker.AsyncMock,
        )

        result = await avatar_file_dependency(mock_request)
        assert result is not None


@pytest.mark.asyncio
class TestFileCoreSecurityUnit:
    """Юнит-тесты глубокого трехконтурного валидатора файлов."""

    async def test_validate_file_core_empty_name_fails(self, mocker) -> None:
        """Тест: файл без имени или расширения возвращает 400."""
        mock_file = mocker.Mock()
        mock_file.filename = 'no_extension'

        with pytest.raises(HTTPException) as exc:
            await dependency._validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 400

        detail_dict = exc.value.detail
        assert detail_dict.get('msg') == constants.NOT_ALLOWED_FILE_NAME

    async def test_validate_file_core_size_exceeded_413(self, mocker) -> None:
        """Тест: превышение лимита веса возвращает 413."""
        mock_file = mocker.Mock()
        mock_file.filename = 'photo.png'
        mock_file.size = 5 * 1024 * 1024

        with pytest.raises(HTTPException) as exc:
            await dependency._validate_file_core(
                file=mock_file,
                allow_file_size=2 * 1024 * 1024,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 413

        detail_dict = exc.value.detail
        assert detail_dict.get('msg') == constants.NOT_ALLOWED_FILE_SIZE

    async def test_validate_file_core_dangerous_extension_ban(
        self, mocker
    ) -> None:
        """Тест Контура 1: прямой запрет на .exe из черного списка."""
        mock_file = mocker.Mock()
        mock_file.filename = 'payload.exe'
        # Обходим валидатор размера Mock > int
        mock_file.size = 100

        with pytest.raises(HTTPException) as exc:
            await dependency._validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_validate_file_core_double_extension_ban(
        self, mocker
    ) -> None:
        """Тест: маскировка скрытого расширения (test.exe.png)."""
        mock_file = mocker.Mock()
        mock_file.filename = 'malware.exe.png'
        # Обходим валидатор размера Mock > int
        mock_file.size = 100

        with pytest.raises(HTTPException) as exc:
            await dependency._validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_validate_file_core_binary_signature_ban(
        self, mocker
    ) -> None:
        """Тест Контура 3: бинарный сканер выявляет замаскированный софт."""
        mock_guess = mocker.patch('filetype.guess')
        mock_file = mocker.AsyncMock()
        mock_file.filename = 'fake_image.png'
        mock_file.size = 500
        mock_file.read.return_value = b'some_bytes'

        mock_kind = mocker.Mock()
        mock_kind.mime = 'application/x-msdownload'
        mock_guess.return_value = mock_kind

        with pytest.raises(HTTPException) as exc:
            await dependency._validate_file_core(
                file=mock_file,
                allow_file_size=2000,
                expected_types=['image/png'],
                allow_extensions=AvatarMIMEType,
            )
        assert exc.value.status_code == 415

        detail_dict = exc.value.detail
        assert (
            detail_dict.get('msg')
            == 'Загрузка исполняемых файлов категорически запрещена.'
        )


@pytest.mark.asyncio
class TestAttachmentsFilesDependencyUnit:
    """Юнит-тесты пакетного валидатора вложений к карточкам задач."""

    async def test_attachments_dependency_empty_list_fails(
        self, mocker
    ) -> None:
        """Тест: отправка пустого пакета файлов возвращает 400."""
        mock_request = mocker.AsyncMock()
        mock_form = mocker.MagicMock()
        mock_form.getlist.return_value = []
        mock_request.form.return_value = mock_form

        with pytest.raises(HTTPException) as exc:
            # Передаем пустой список в files для обхода TypeError
            await attachments_files_dependency(files=[])

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST

    async def test_attachments_dependency_success_skips_strings(
        self, mocker
    ) -> None:
        """Тест: пачка файлов проходит, а пустые строки пропускаются."""
        mock_file_1 = mocker.Mock(spec=mocker.MagicMock)
        mock_file_1.filename = 'report.txt'
        mock_file_1.size = 100

        mocker.patch(
            'core.dependency._validate_file_core',
            new_callable=mocker.AsyncMock,
        )

        # Передаем массив напрямую в ТЗ-аргумент files
        result = await attachments_files_dependency(files=[mock_file_1, ''])
        assert len(result) == 1
        assert result[0] == mock_file_1
