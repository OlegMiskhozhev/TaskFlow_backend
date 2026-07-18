from pydantic import BaseModel, ConfigDict, Field

from models.enums import TaskListStatus
from schemas.tasks import TaskInfo


class TaskListCreate(BaseModel):
    """Схема валидации списка задач."""

    name: str = Field(description='Наименование списка задач')


class TaskListUpdate(BaseModel):
    """Схема валидации списка задач."""

    name: str | None = Field(
        default=None, description='Наименование списка задач'
    )
    status: TaskListStatus | None = Field(
        default=None, description='Статус списка задач'
    )


class TaskListDetail(TaskListCreate):
    """Схема представления списка задач проекта."""

    id: int = Field(description='Идентификатор списка задач')
    status: TaskListStatus = Field(description='Статус списка задач')
    tasks: list[TaskInfo] = Field(description='Задачи')
    model_config = ConfigDict(from_attributes=True)


class TaskListSortRequest(BaseModel):
    """Схема валидации параметров пользовательской сортировки задач."""

    tasklist_id: int = Field(title='Идентификатор перемещаемого списка задач')
    new_previous_tasklist_id: int | None = Field(
        default=None,
        title='Идентификатор нового предидущего списка',
        description='Null - переместить в начало',
    )
