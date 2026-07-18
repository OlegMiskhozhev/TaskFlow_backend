from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from schemas.projects import ProjectCreate, ProjectUpdate


class TestProjectCreateSchemaUnit:
    """Юнит-тесты валидации полей схемы создания проекта ProjectCreate."""

    def test_deadline_validation_fails_when_deadline_in_past(self):
        """Тест: вчерашний дедлайн вызывает ошибку ValidationError."""
        # Ставим вчерашний день
        past_datetime = datetime.now(UTC) - timedelta(days=1)

        # Исправлено: ловим каноничный ValidationError верхнего уровня Pydantic
        with pytest.raises(ValidationError) as exc:
            ProjectCreate(
                name='Test Project',
                deadline=past_datetime,
                user_timezone='UTC',
            )
        assert 'не может быть ранее' in str(exc.value)

    def test_deadline_validation_passes_with_current_and_future_date(self):
        """Тест: сегодняшний или будущий дедлайн успешно проходят."""
        # Сегодняшний день (должен пройти по логике .date() в схеме)
        current_datetime = datetime.now(UTC)
        project_today = ProjectCreate(
            name='Today Project',
            deadline=current_datetime,
            user_timezone='UTC',
        )
        assert project_today.name == 'Today Project'

        # Будущий день
        future_datetime = datetime.now(UTC) + timedelta(days=10)
        project_future = ProjectCreate(
            name='Future Project',
            deadline=future_datetime,
            user_timezone='UTC',
        )
        assert project_future.name == 'Future Project'


class TestProjectUpdateSchemaUnit:
    """Юнит-тесты валидации полей схемы обновления проекта ProjectUpdate."""

    def test_deadline_validation_with_deadline_in_past_raises_error(self):
        """Тест: обновление дедлайна на прошедший день вызывает ошибку."""
        past_datetime = datetime.now(UTC) - timedelta(days=1)

        # Исправлено: ловим ValidationError вместо сырого PydanticCustomError
        with pytest.raises(ValidationError) as exc:
            ProjectUpdate(
                deadline=past_datetime,
                user_timezone='UTC',
            )
        assert 'не может быть ранее' in str(exc.value)

    def test_deadline_validation_with_future_date_passes(self):
        """Тест: обновление дедлайна на будущее время проходит успешно."""
        future_datetime = datetime.now(UTC) + timedelta(days=10)

        project = ProjectUpdate(
            deadline=future_datetime,
            user_timezone='UTC',
        )
        assert project.deadline is not None
