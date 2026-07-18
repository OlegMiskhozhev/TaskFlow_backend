from pydantic import BaseModel, ConfigDict, Field


class AttachmentRead(BaseModel):
    """Схема ответа для одного вложения."""

    id: int = Field(description='Идентификатор вложения')
    filename: str = Field(description='Имя файла с расширением')
    size: int = Field(description='Размер файла в байтах')
    url: str | None = Field(
        default=None, description='Ссылка на файл в хранилище'
    )
    model_config = ConfigDict(from_attributes=True)


class AttachmentsList(BaseModel):
    """Схема ответа для списка вложений."""

    attachments: list[AttachmentRead] = Field(
        default=[], description='Список вложений.'
    )


class AttachmentsBind(BaseModel):
    """Схема привязки уже загруженных вложений к задаче."""

    attachment_ids: list[int] = Field(
        min_length=1, description='Список идентификаторов вложений.'
    )
