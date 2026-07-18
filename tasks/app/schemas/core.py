from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema

from models.enums import Timezone
from models.taskflow import Project, Subtask, Task, TaskList


class Message(BaseModel):
    """Схема ответа в формате сообщения."""

    message: str = Field(title='Сообщение сервера')


class PathObjects(BaseModel):
    """Схема для валидации параметров пути запроса."""

    project: Project | None
    tasklist: TaskList | None = Field(default=None)
    task: Task | None = Field(default=None)
    subtask: Subtask | None = Field(default=None)
    model_config = ConfigDict(arbitrary_types_allowed=True)


class UserTimezone(BaseModel):
    """Схема добавления поля часового пояса пользователя в схемы валидации."""

    user_timezone: SkipJsonSchema[Timezone] | None = Field(
        default=Timezone.UTC, title='Часовой пояс пользователя', exclude=True
    )
