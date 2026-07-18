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

from models.enums import (
    ReminderPeriodic,
    SubtaskStatus,
    TaskPriority,
    TaskStatus,
)
from schemas.attachments import AttachmentRead
from schemas.core import UserTimezone
from schemas.subtasks import SubtaskDetail
from schemas.tags import TagDetail


class ProjectDeadline(BaseModel):
    """Схема сериализации дедлайна текущего проекта."""

    deadline: datetime = Field(title='Дата завершения проекта')
    model_config = ConfigDict(from_attributes=True)


class TaskCreate(UserTimezone):
    """Схема валидации данных для создания задачи."""

    name: str = Field(title='Название задачи', min_length=3, max_length=150)
    status: TaskStatus = Field(
        default=TaskStatus.IN_PROGRESS, title='Статус задачи'
    )
    priority: TaskPriority | None = Field(
        default=TaskPriority.LOW, title='Приоритет задачи'
    )

    @computed_field(title='Дата создания задачи')
    def created_at(self) -> datetime:
        user_now = datetime.now(ZoneInfo(self.user_timezone.value))
        return user_now.astimezone(ZoneInfo('UTC'))


class TaskInfo(UserTimezone):
    """Схема представления информации для карточки задачи."""

    id: int = Field(title='Идентификатор задачи')
    tasklist_id: int = Field(title='Идентификатор списка задач')
    name: str = Field(title='Название задачи')
    status: TaskStatus = Field(title='Статус задачи')
    priority: TaskPriority = Field(title='Приоритет задачи')
    created_at: datetime = Field(title='Дата создания задачи')
    start_at: datetime | None = Field(
        default=None, title='Дата и время начала задачи', exclude=True
    )
    deadline: datetime | None = Field(
        default=None, title='Дата и время начала задачи', exclude=True
    )
    tags: list[TagDetail] | None = Field(default=[], title='Теги задачи')
    subtasks: list[SubtaskDetail] | None = Field(default=[], title='Подзадачи')
    attachments: list[AttachmentRead] | None = Field(
        default=[], title='Вложения', exclude=True
    )
    model_config = ConfigDict(from_attributes=True)

    # Внутренний кэш для предотвращения 6-кратной инициализации ZoneInfo
    _local_start: datetime | None = None
    _local_deadline: datetime | None = None

    @model_validator(mode='after')
    def _localize_datetimes(self) -> Self:
        """Один раз кэширует локализованные даты в ОЗУ схемы."""
        tz = ZoneInfo(self.user_timezone.value)
        if self.start_at:
            self._local_start = self.start_at.astimezone(tz)
        if self.deadline:
            self._local_deadline = self.deadline.astimezone(tz)
        return self

    @computed_field(title='Дата начала задачи')
    @property
    def start_at_date(self) -> date | None:
        return self._local_start.date() if self._local_start else None

    @computed_field(title='Час начала задачи')
    @property
    def start_at_hour(self) -> int | None:
        return self._local_start.hour if self._local_start else None

    @computed_field(title='Минуты начала задачи')
    @property
    def start_at_minutes(self) -> int | None:
        return self._local_start.minute if self._local_start else None

    @computed_field(title='Дата завершения задачи')
    @property
    def deadline_date(self) -> date | None:
        return self._local_deadline.date() if self._local_deadline else None

    @computed_field(title='Час завершения задачи')
    @property
    def deadline_hour(self) -> int | None:
        return self._local_deadline.hour if self._local_deadline else None

    @computed_field(title='Минуты завершения задачи')
    @property
    def deadline_minutes(self) -> int | None:
        return self._local_deadline.minute if self._local_deadline else None

    @computed_field(title='Количество всех подзадач')
    @property
    def subtasks_all(self) -> int:
        return len(self.subtasks) if self.subtasks else 0

    @computed_field(title='Количество завершенных подзадач')
    @property
    def subtasks_done(self) -> int:
        if not self.subtasks:
            return 0
        # Оптимизировано: ленивое суммирование без выделения памяти
        return sum(1 for s in self.subtasks if s.status == SubtaskStatus.DONE)

    @computed_field(title='Наличие вложений')
    @property
    def has_attachments(self) -> bool:
        return bool(self.attachments)

    @field_serializer('created_at')
    def format_created_at(self, created_at: datetime) -> date:
        tz = ZoneInfo(self.user_timezone.value)
        return created_at.astimezone(tz).date()


class TaskDetail(TaskInfo):
    """Схема представления полной информации о задаче."""

    description: str | None = Field(default=None, title='Описание задачи')
    attachments: list[AttachmentRead] | None = Field(
        default=[], title='Вложения'
    )
    reminder_datetime: datetime | None = Field(
        default=None, title='Дата напоминания', exclude=True
    )
    reminder_periodic: ReminderPeriodic | None = Field(
        default=None, title='Периодичность напоминаний'
    )

    _local_reminder: datetime | None = None

    @model_validator(mode='after')
    def _localize_reminder(self) -> Self:
        if self.reminder_datetime:
            tz = ZoneInfo(self.user_timezone.value)
            self._local_reminder = self.reminder_datetime.astimezone(tz)
        return self

    @computed_field(title='Дата напоминания')
    @property
    def reminder_date(self) -> date | None:
        return self._local_reminder.date() if self._local_reminder else None

    @computed_field(title='Час напоминания')
    @property
    def reminder_time_hour(self) -> int | None:
        return self._local_reminder.hour if self._local_reminder else None

    @computed_field(title='Минуты напоминания')
    @property
    def reminder_time_minutes(self) -> int | None:
        return self._local_reminder.minute if self._local_reminder else None


class TaskBaseUpdate(UserTimezone):
    """Базовая схема для обновления задачи."""

    task: SkipJsonSchema[TaskInfo] | None = Field(
        default=None,
        title='Обновляемая задача',
        exclude=True,
    )
    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )


class TaskInfoUpdate(TaskBaseUpdate):
    """Схема для обновления информации о задаче."""

    name: str | None = Field(default=None, title='Название задачи')
    priority: TaskPriority | None = Field(
        default=None, title='Приоритет задачи'
    )
    description: str | None = Field(default=None, title='Описание задачи')

    @model_validator(mode='after')
    def check_status(self) -> Self:
        if self.task and self.task.status == TaskStatus.DONE:
            raise PydanticCustomError(
                'validation_error',
                'Нельзя редактировать завершенную задачу.',
                {'field': 'status'},
            )
        return self


class TaskPeriodUpdate(TaskBaseUpdate):
    """Схема валидации обновления сроков выполнения задачи."""

    project: SkipJsonSchema[ProjectDeadline] | None = Field(
        default=None,
        title='Обновляемый проект',
        exclude=True,
    )
    start_at_date: date | None = Field(
        default=None, title='Дата начала задачи', exclude=True
    )
    start_at_hour: int | None = Field(
        ge=0, le=23, default=0, title='Час начала задачи', exclude=True
    )
    start_at_minutes: int | None = Field(
        ge=0, le=59, default=0, title='Минуты начала задачи', exclude=True
    )
    deadline_date: date | None = Field(
        default=None, title='Дата завершения задачи', exclude=True
    )
    deadline_hour: int | None = Field(
        ge=0, le=23, default=0, title='Час завершения задачи', exclude=True
    )
    deadline_minutes: int | None = Field(
        ge=0, le=59, default=0, title='Минуты завершения задачи', exclude=True
    )

    def _assemble_tz_datetime(
        self, target_date: date, hour: int, minutes: int
    ) -> datetime:
        """Вспомогательный метод сборки локальной даты-времени в UTC."""
        user_tz = ZoneInfo(self.user_timezone.value)
        naive_dt = datetime.combine(target_date, time(hour, minutes))
        return naive_dt.replace(tzinfo=user_tz).astimezone(ZoneInfo('UTC'))

    @computed_field(title='Дата и время начала задачи')
    def start_at(self) -> datetime | None:
        if self.start_at_date:
            return self._assemble_tz_datetime(
                self.start_at_date, self.start_at_hour, self.start_at_minutes
            )
        return self.task.start_at if self.task else None

    @computed_field(title='Дата и время завершения задачи')
    def deadline(self) -> datetime | None:
        if self.deadline_date:
            return self._assemble_tz_datetime(
                self.deadline_date, self.deadline_hour, self.deadline_minutes
            )
        return self.task.deadline if self.task else None

    @computed_field(title='Статус задачи')
    def status(self) -> TaskStatus:
        status = TaskStatus.IN_PROGRESS
        if self.start_at:
            if self.start_at > datetime.now(ZoneInfo('UTC')):
                status = TaskStatus.SCHEDULE
        return status

    @model_validator(mode='after')
    def check_status(self) -> Self:
        if self.task and self.task.status == TaskStatus.DONE:
            raise PydanticCustomError(
                'validation_error',
                'Нельзя редактировать завершенную задачу.',
                {'field': 'status'},
            )
        return self

    @model_validator(mode='after')
    def validate_period(self) -> Self:
        if self.task and self.project:
            if self.deadline and self.start_at:
                if self.deadline < self.start_at:
                    raise PydanticCustomError(
                        'validation_error',
                        'Срок завершения задачи не может быть ранее '
                        'срока начала ее выполнения.',
                        {'field': 'deadline'},
                    )
            if self.start_at_date and self.start_at:
                tz = ZoneInfo(self.user_timezone.value)
                if self.start_at.astimezone(tz) < datetime.now(tz):
                    raise PydanticCustomError(
                        'validation_error',
                        'Срок начала задачи не может быть ранее '
                        'текущего времени.',
                        {'field': 'start_at'},
                    )
                if self.start_at.date() > self.project.deadline.date():
                    raise PydanticCustomError(
                        'validation_error',
                        'Дата начала задачи не может быть позже даты '
                        'завершения проекта.',
                        {'field': 'start_at'},
                    )
            if self.deadline:
                tz = ZoneInfo(self.user_timezone.value)
                if self.deadline.astimezone(tz) < datetime.now(tz):
                    raise PydanticCustomError(
                        'validation_error',
                        'Срок завершения задачи не может быть ранее '
                        'текущего времени.',
                        {'field': 'deadline'},
                    )
                if self.deadline.date() > self.project.deadline.date():
                    raise PydanticCustomError(
                        'validation_error',
                        'Дата завершения задачи не может быть позже '
                        'даты завершения проекта.',
                        {'field': 'deadline'},
                    )
        return self


class TaskStatusUpdate(TaskBaseUpdate):
    """Схема валидации обновления статуса задачи."""

    status: TaskStatus = Field(title='Статус задачи')

    @model_validator(mode='after')
    def validate_status(self) -> Self:
        if self.task and self.status == TaskStatus.SCHEDULE:
            if not self.task.start_at:
                raise PydanticCustomError(
                    'validation_error',
                    'Установите дату и время начала выполнения задачи '
                    'для установки статуса <Запланировано>.',
                    {'field': 'status'},
                )
            elif self.task.start_at < datetime.now(ZoneInfo('UTC')):
                raise PydanticCustomError(
                    'validation_error',
                    'Статус <Запланировано> нельзя установить для задачи, '
                    'для которой начало выполнения установлено ранее '
                    'текущего времени.',
                    {'field': 'status'},
                )
        return self


class TaskMove(TaskBaseUpdate):
    """Схема валидации для перемещения задачи в другой список."""

    tasklist_id: int = Field(title='Идентификатор нового списка задач')
