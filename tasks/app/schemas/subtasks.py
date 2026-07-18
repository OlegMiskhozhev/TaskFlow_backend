from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from models.enums import SubtaskStatus


class SubtaskCreate(BaseModel):
    """Схема валидации входящих данных при создании подзадачи."""

    name: str = Field(title='Название подзадачи', min_length=3, max_length=100)
    status: SubtaskStatus = Field(
        default=SubtaskStatus.IN_PROGRESS, description='Статус подзадачи'
    )


class SubtaskDetail(SubtaskCreate):
    """Схема представления данных подзадачи."""

    id: int = Field(description='Идентификатор подзадачи')
    model_config = ConfigDict(from_attributes=True)


class SubtaskUpdate(BaseModel):
    """Схема валидации обновления подзадачи."""

    name: str | None = Field(
        default=None, description='Наименование подзадачи'
    )
    status: SubtaskStatus | None = Field(
        default=None, description='Статус подзадачи'
    )
    subtask: SkipJsonSchema[Any] | None = Field(default=None, exclude=True)
    model_config = ConfigDict(
        validate_assignment=True, arbitrary_types_allowed=True
    )

    @model_validator(mode='after')
    def check_subtask_status(self) -> Self:
        """Бизнес-правило: закрытую подзадачу нельзя редактировать."""
        if self.subtask and self.subtask.status == SubtaskStatus.DONE:
            raise PydanticCustomError(
                'validation_error',
                'Нельзя редактировать завершенную подзадачу.',
                {'field': 'status'},
            )
        return self
