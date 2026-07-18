from datetime import date, datetime, time
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from models.enums import ReminderPeriodic, TaskStatus


class CurrentTask(BaseModel):
    """Схема сериализации текущей задачи."""

    id: int
    status: TaskStatus
    start_at: datetime | None
    deadline: datetime | None
    model_config = ConfigDict(from_attributes=True)


class CreateReminder(BaseModel):
    """Схема валидации создания напоминания."""

    task: CurrentTask | None = Field(
        default=None,
        title='Обновляемый проект',
        exclude=True,
    )
    reminder_date: date = Field(description='Дата напоминания', exclude=True)
    reminder_time_hour: int = Field(
        default=8, ge=0, le=23, description='Час напоминания', exclude=True
    )
    reminder_time_minutes: int = Field(
        default=0, ge=0, le=59, description='Минуты напоминания', exclude=True
    )
    reminder_periodic: ReminderPeriodic = Field(
        default=ReminderPeriodic.NONE,
        description='Периодичность напоминания',
    )
    user_timezone: str = Field(default='UTC', exclude=True)
    model_config = ConfigDict(
        validate_assignment=True, arbitrary_types_allowed=True
    )

    @computed_field(title='Дата и время напоминания')
    def reminder_datetime(self) -> datetime:
        user_tz = ZoneInfo(self.user_timezone)
        naive_dt = datetime.combine(
            self.reminder_date,
            time(self.reminder_time_hour, self.reminder_time_minutes),
        )
        return naive_dt.replace(tzinfo=user_tz).astimezone(ZoneInfo('UTC'))

    @model_validator(mode='after')
    def reminder_validator(self) -> Self:
        if self.task and self.task.status == TaskStatus.DONE:
            raise PydanticCustomError(
                'validation_error',
                'Нельзя установить напоминание для завершенной задачи.',
                {'field': 'status'},
            )
        return self

    @model_validator(mode='after')
    def reminder_periodic_validator(self) -> Self:
        if (
            self.task
            and not self.task.deadline
            and self.reminder_periodic != ReminderPeriodic.NONE
        ):
            raise PydanticCustomError(
                'validation_error',
                (
                    'Установите дату завершения задачи '
                    'для использования повторов.'
                ),
                {'field': 'reminder_periodic'},
            )
        return self

    @model_validator(mode='after')
    def reminder_date_validator(self) -> Self:
        if self.task:
            if self.reminder_datetime < datetime.now(ZoneInfo('UTC')):
                raise PydanticCustomError(
                    'validation_error',
                    'Напоминание не может быть установлено в прошлом.',
                    {'field': 'reminder_date'},
                )
            if (
                self.task.start_at
                and self.reminder_datetime < self.task.start_at
            ):
                raise PydanticCustomError(
                    'validation_error',
                    'Напоминание не может быть ранее начала задачи.',
                    {'field': 'reminder_date'},
                )
            if (
                self.task.deadline
                and self.reminder_datetime > self.task.deadline
            ):
                raise PydanticCustomError(
                    'validation_error',
                    'Напоминание не может быть позже дедлайна задачи.',
                    {'field': 'reminder_date'},
                )
        return self


class ReminderTask(BaseModel):
    """Схема сериализации связанной с напоминанием задачи."""

    name: str
    description: str | None
    deadline: datetime | None
    status: TaskStatus
    model_config = ConfigDict(from_attributes=True)


class ReminderUpdate(BaseModel):
    """Схема валидации изменения напоминания."""

    was_read: bool = Field(title='Отметка о прочтении')


class ReminderInfo(ReminderUpdate):
    """Схема представления напоминания."""

    id: int = Field(title='Идентификатор напоминания')
    send_time: datetime = Field(
        title='Дата и время отправки напоминания', exclude=True
    )
    task: ReminderTask = Field(title='Задача', exclude=True)
    user_timezone: str = Field(default='UTC', exclude=True)
    model_config = ConfigDict(from_attributes=True)

    @computed_field(title='Название задачи')
    @property
    def task_name(self) -> str:
        return self.task.name if self.task else ''

    @computed_field(title='Описание задачи')
    @property
    def task_description(self) -> str | None:
        return self.task.description if self.task else None

    @computed_field(title='Статус задачи')
    @property
    def task_status(self) -> TaskStatus | None:
        return self.task.status if self.task else None

    @computed_field(title='Дата отправки напоминания')
    @property
    def sent_date(self) -> date | None:
        if self.send_time:
            return self.send_time.astimezone(
                ZoneInfo(self.user_timezone)
            ).date()
        return None

    @computed_field(title='Час отправки напоминания')
    @property
    def sent_time_hour(self) -> int | None:
        if self.send_time:
            return self.send_time.astimezone(ZoneInfo(self.user_timezone)).hour
        return None

    @computed_field(title='Минуты отправки напоминания')
    @property
    def sent_time_minutes(self) -> int | None:
        if self.send_time:
            return self.send_time.astimezone(
                ZoneInfo(self.user_timezone)
            ).minute
        return None

    @computed_field(title='Состояние дедлайна задачи')
    @property
    def expired(self) -> bool:
        if self.task and self.task.deadline:
            return self.task.deadline < datetime.now(ZoneInfo('UTC'))
        return False


class UserReminders(BaseModel):
    """Схема представления списка напоминаний."""

    reminders: list[ReminderInfo] = Field(
        default=[], title='Напоминания пользователя'
    )
