import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from models.enums import Timezone


class PasswordRequest(BaseModel):
    """Схема валидации запроса на установку пароля пользователя."""

    password: str = Field(
        min_length=12,
        max_length=100,
        pattern=re.compile(
            r'^(?=.*[A-Z])'
            r'(?=.*[a-z])'
            r'(?=.*\d)'
            r'(?=.*[!%^*()_+=\[\]{};":\|,.*?\/])'
            r'[A-Za-z0-9!%^*()_+=\[\]{};":\|,.*?\/]{12,100}$'
        ),
        title='Пароль',
    )
    confirm_password: str = Field(title='Подтверждение пароля')

    @model_validator(mode='after')
    def check_passwords_match(self) -> Self:
        """Проверить совпадение пароля и подтверждения."""
        if self.password != self.confirm_password:
            raise PydanticCustomError(
                'validation_error',
                'Пароли не совпадают. Пожалуйста, введите одинаковые пароли',
                {'field': 'confirm_password'},
            )
        return self

    @model_validator(mode='after')
    def check_forbidden_chars(self) -> Self:
        """Проверить наличие опасных и запрещенных символов."""
        forbidden = '\\/;\'"--#<>$&@'
        found = [c for c in self.password if c in forbidden]
        if found:
            raise PydanticCustomError(
                'validation_error',
                f'Пароль содержит запрещенные символы: {forbidden}',
                {'field': 'password'},
            )
        return self


class RecoveryRequest(BaseModel):
    """Схема валидации запроса на восстановление пароля по Email."""

    email: str = Field(title='Адрес электронной почты пользователя')

    @model_validator(mode='after')
    def validate_email_length(self) -> Self:
        """Проверить длину частей email-адреса."""
        v = self.email
        if '@' not in v:
            raise PydanticCustomError(
                'validation_error',
                'Неверный формат Email.',
                {'field': 'email'},
            )
        parts = v.split('@')
        if len(parts[0]) > 64 or len(parts[1]) > 159 or len(v) > 254:
            raise PydanticCustomError(
                'validation_error',
                'Превышена допустимая длина Email.',
                {'field': 'email'},
            )
        return self


class RegisterRequest(PasswordRequest, RecoveryRequest):
    """Схема валидации запроса на регистрацию пользователя."""

    @model_validator(mode='after')
    def check_email_not_in_password(self) -> Self:
        """Запретить использование логина почты внутри тела пароля."""
        email_prefix = self.email.split('@')[0].lower()
        if email_prefix in self.password.lower():
            raise PydanticCustomError(
                'validation_error',
                'Пароль не должен содержать email пользователя.',
                {'field': 'password'},
            )
        return self

    @model_validator(mode='after')
    def validate_email_format(self) -> Self:
        """Проверить запрещенные символы и спец-последовательности."""
        v = self.email
        forbidden = '\'"\\;#,<>/& '
        if (
            any(c in v for c in forbidden)
            or v.startswith(('.', '-'))
            or '..' in v
            or '--' in v
        ):
            raise PydanticCustomError(
                'validation_error',
                'Email содержит недопустимые символы.',
                {'field': 'email'},
            )
        return self


class OAuthLinkResponse(BaseModel):
    """Схема ответа со ссылкой на страницу авторизации провайдера."""

    url: str = Field(..., title='Ссылка для редиректа на сторону сервиса')


class UniversalOAuthRequest(BaseModel):
    """Схема запроса от фронтенда с кодом авторизации."""

    code: str = Field(
        ..., title='Код авторизации, полученный от OAuth провайдера'
    )


class TokensPair(BaseModel):
    """Схема ответа с парой JWT сессионных токенов."""

    access_token: str = Field(title='Токен доступа к сервису.')
    refresh_token: str = Field(title='Токен обновления токена доступа.')


class UserUpdate(BaseModel):
    """Схема валидации запроса на изменения данных пользователя."""

    username: str | None = Field(
        min_length=2, default=None, title='Имя пользователя.'
    )
    timezone: Timezone | None = Field(default=None, title='Часовой пояс.')


class Avatar(BaseModel):
    """Схема представления ссылки на аватар."""

    avatar_url: str | None = Field(
        default=None, title='Ссылка на файл аватара пользователя.'
    )


class UserProject(BaseModel):
    """Схема представления проекта в профиле пользователя."""

    id: int = Field(title='Идентификатор проекта')
    name: str = Field(title='Наименование проекта')
    model_config = ConfigDict(from_attributes=True)


class UserDetail(RecoveryRequest, Avatar, UserUpdate):
    """Схема представления данных профиля пользователя."""

    id: int = Field(title='Идентификатор пользователя.')
    projects: list[UserProject] = Field(
        default=[], title='Список активных проектов пользователя.'
    )
    model_config = ConfigDict(from_attributes=True)


class UserId(BaseModel):
    """Схема ответа с id текущего пользователя."""

    id: int = Field(title='Идентификатор пользователя.')
