from datetime import date, datetime, time
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from core import constants
from models.enums import ProjectStatus, TaskStatus
from schemas.core import UserTimezone
from schemas.tasklist import TaskListDetail


class ProjectCreate(UserTimezone):
    """Схема валидации входящих данных для создания проекта."""

    name: str = Field(title='Наименование проекта')
    status: ProjectStatus = Field(
        default=ProjectStatus.IN_PROGRESS, title='Статус проекта'
    )
    deadline: datetime = Field(title='Дата завершения проекта')
    description: str | None = Field(default=None, title='Описание проекта')
    model_config = ConfigDict(validate_assignment=True)

    @field_serializer('deadline')
    def format_deadline(self, deadline: datetime) -> datetime:
        """Форматировать дату завершения проекта."""
        user_tz = ZoneInfo(self.user_timezone.value)
        naive_end = datetime.combine(deadline.date(), time(23, 59, 59))
        localized_deadline = naive_end.replace(tzinfo=user_tz)
        return localized_deadline.astimezone(ZoneInfo('UTC'))

    @computed_field(title='Дата создания проекта')
    def created_at(self) -> datetime:
        user_now = datetime.now(ZoneInfo(self.user_timezone.value))
        return user_now.astimezone(ZoneInfo('UTC'))

    @model_validator(mode='after')
    def deadline_validate(self) -> Self:
        """Валидировать время завершения проекта."""
        user_now = datetime.now(ZoneInfo(self.user_timezone.value)).date()
        deadline = datetime.combine(self.deadline, time(23, 59, 59)).date()
        if user_now > deadline:
            raise PydanticCustomError(
                'validation_error',
                'Дата завершения проекта не может быть ранее текущей даты.',
                {'field': 'deadline'},
            )
        return self


class ProjectInfo(UserTimezone):
    """Схема представления краткой информации о проекте."""

    id: int = Field(title='Идентификатор проекта')
    created_at: datetime = Field(title='Дата создания проекта')
    name: str = Field(title='Наименование проекта')
    status: ProjectStatus = Field(title='Статус проекта')
    deadline: datetime = Field(title='Дата завершения проекта')
    tasklists: list[TaskListDetail] | None = Field(
        default=None, title='Списки задач', exclude=True
    )
    model_config = ConfigDict(from_attributes=True)

    @field_serializer('created_at')
    def format_created_at(self, created_at: datetime) -> date:
        """Форматировать дату создания проекта."""
        return created_at.astimezone(ZoneInfo(self.user_timezone.value)).date()

    @field_serializer('deadline')
    def format_deadline(self, deadline: datetime) -> date:
        """Форматировать дату завершения проекта."""
        return deadline.astimezone(ZoneInfo(self.user_timezone.value)).date()

    @computed_field(title='Количество всех задач')
    @property
    def tasks_count_all(self) -> int:
        if not self.tasklists:
            return 0
        return sum(len(tl.tasks) for tl in self.tasklists if tl.tasks)

    @computed_field(title='Количество всех завершенных задач')
    @property
    def tasks_count_done(self) -> int:
        if not self.tasklists:
            return 0
        return sum(
            len([t for t in tl.tasks if t.status == TaskStatus.DONE])
            for tl in self.tasklists
            if tl.tasks
        )


class ProjectsList(BaseModel):
    """Схема представления списка проектов."""

    projects: list[ProjectInfo] = Field(description='Список проектов')
    model_config = ConfigDict(from_attributes=True)


class ProjectDetail(ProjectInfo):
    """Схема представления полных данных проекта."""

    description: str | None = Field(default=None, title='Описание проекта')
    tasklists: list[TaskListDetail] | None = Field(
        default=None, title='Списки задач'
    )
    model_config = ConfigDict(from_attributes=True)


class ProjectUpdate(UserTimezone):
    """Схема валидации данных для обновления проекта."""

    project: SkipJsonSchema[ProjectInfo] | None = Field(
        default=None,
        title='Обновляемый проект',
        exclude=True,
    )
    name: str | None = Field(default=None, title='Наименование проекта')
    status: ProjectStatus | None = Field(default=None, title='Статус проекта')
    deadline: datetime | None = Field(
        default=None, title='Дата завершения проекта'
    )
    description: str | None = Field(default=None, title='Описание проекта')
    model_config = ConfigDict(
        validate_assignment=True, arbitrary_types_allowed=True
    )

    @field_serializer('deadline')
    def format_deadline(self, deadline: datetime) -> datetime | None:
        """Форматировать дату завершения проекта."""
        if deadline:
            user_tz = ZoneInfo(self.user_timezone.value)
            naive_end = datetime.combine(deadline.date(), time(23, 59, 59))
            localized_deadline = naive_end.replace(tzinfo=user_tz)
            return localized_deadline.astimezone(ZoneInfo('UTC'))
        return deadline

    @model_validator(mode='after')
    def status_validate(self) -> Self:
        """Проверить статус проекта."""
        if (
            self.project
            and self.project.status == ProjectStatus.ARCHIVE
            and not self.status
        ):
            raise PydanticCustomError(
                'validation_error',
                constants.ARCHIVE_PROJECT,
                {'field': 'status'},
            )
        return self

    @model_validator(mode='after')
    def deadline_validate(self) -> Self:
        """Проверить новую дату завершения проекта."""
        if self.deadline:
            user_now = datetime.now(ZoneInfo(self.user_timezone.value)).date()
            deadline = datetime.combine(self.deadline, time(23, 59, 59)).date()

            if user_now > deadline:
                raise PydanticCustomError(
                    'validation_error',
                    'Дата завершения проекта не может быть ранее '
                    'текущей даты.',
                    {'field': 'deadline'},
                )

            unsuitable_tasks = []
            if self.project:
                for tasklist in self.project.tasklists:
                    if tasklist.tasks:
                        tasks = [
                            t
                            for t in tasklist.tasks
                            if (
                                (t.start_at and t.start_at.date() > deadline)
                                or (
                                    t.deadline and t.deadline.date() > deadline
                                )
                            )
                        ]
                        unsuitable_tasks += tasks

            if unsuitable_tasks:
                tasks_names = [t.name for t in unsuitable_tasks]
                raise PydanticCustomError(
                    'validation_error',
                    (
                        f'Для следующих задач: {tasks_names} установлены '
                        f'сроки ранее {self.deadline.date()}. Измените сроки '
                        f'этих задач, чтобы изменить срок завершения проекта'
                    ),
                    {'field': 'deadline'},
                )
        return self
