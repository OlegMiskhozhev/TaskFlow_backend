from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base
from models.enums import Timezone, UserRole
from models.taskflow import Project, Tag


class Avatar(Base):
    """Модель аватара пользователя."""

    filename: Mapped[str]
    minio_name: Mapped[str]
    mime_type: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    user: Mapped['User'] = relationship(
        'User', back_populates='avatar', uselist=False
    )

    __table_args__ = (
        # Ускоряет get_user_detail при ленивой проверке аватара
        Index('idx_avatars_user_id', 'user_id'),
    )


class User(Base):
    """Модель пользователя."""

    email: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str] = mapped_column(String(100))
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=True
    )
    timezone: Mapped[Timezone] = mapped_column(default=Timezone.UTC)
    is_active: Mapped[bool] = mapped_column(default=False)
    is_blocked: Mapped[bool] = mapped_column(default=False)
    role: Mapped[UserRole] = mapped_column(
        default=UserRole.USER, server_default=UserRole.USER.name
    )
    avatar: Mapped['Avatar'] = relationship(
        'Avatar', back_populates='user', lazy='joined'
    )
    tokens: Mapped[list['Token']] = relationship(
        'Token',
        back_populates='user',
        cascade='all, delete-orphan',
    )
    projects: Mapped[list['Project']] = relationship(
        'Project',
        back_populates='user',
        cascade='all, delete-orphan',
        lazy='selectin',
    )
    tags: Mapped[list['Tag']] = relationship(
        'Tag',
        back_populates='user',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    __table_args__ = (
        # Функциональный индекс для регистронезависимого поиска
        # (get_user_by_email)
        Index('idx_users_email_lower', func.lower('email')),
    )


class Token(Base):
    """Модель для хранения токенов."""

    access_token: Mapped[str]
    refresh_token: Mapped[str]
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE')
    )
    user: Mapped['User'] = relationship(
        'User', back_populates='tokens', lazy='joined'
    )
    is_active: Mapped[bool]

    __table_args__ = (
        # Ускоряет проверку сессии на каждом запросе в AuthDependency
        Index('idx_tokens_access_token', 'access_token'),
        # Ускоряет ручку /refresh
        Index('idx_tokens_refresh_token', 'refresh_token'),
        # Ускоряет каскадную склейку joinedload(Token.user)
        Index('idx_tokens_user_id', 'user_id'),
    )
