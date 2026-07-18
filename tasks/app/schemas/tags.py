from pydantic import BaseModel, ConfigDict, Field


class TagBase(BaseModel):
    """Базовая схема тега."""

    name: str = Field(description='Наименование тега')
    model_config = ConfigDict(from_attributes=True)


class TagCreate(TagBase):
    """Схема создания тега."""

    model_config = ConfigDict(from_attributes=True)


class TagUpdate(TagBase):
    """Схема обновления тега."""

    model_config = ConfigDict(from_attributes=True)


class TagDetail(TagBase):
    """Схема детального представления тега."""

    id: int = Field(description='Идентификатор тега')
    model_config = ConfigDict(from_attributes=True)


class TagList(BaseModel):
    """Схема списка тегов."""

    tags: list[TagDetail] = Field(default=[])


class TaskTags(BaseModel):
    """Схема для синхронизации тегов задачи."""

    tag_ids: list[int] = Field(
        default=[],
        description='Список ID тегов задачи',
    )
