from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base
from models.base import BaseCreated, BaseName
from models.enums import (
    MIMEType,
    ProjectStatus,
    ReminderChannel,
    ReminderPeriodic,
    ReminderStatus,
    SubtaskStatus,
    TaskListStatus,
    TaskPriority,
    TaskStatus,
)

if TYPE_CHECKING:
    from tasks.app.models.users import User


class Project(BaseCreated, BaseName):
    """Модель проекта."""

    description: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[ProjectStatus]
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE')
    )
    user: Mapped['User'] = relationship(
        'User', back_populates='projects', lazy='joined'
    )
    tasklists: Mapped[list['TaskList']] = relationship(
        'TaskList',
        back_populates='project',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='TaskList.status, TaskList.seq_number',
    )

    __table_args__ = (
        # Ускоряет выборку списка проектов текущего юзера (GET /projects/)
        Index('idx_projects_user_id', 'user_id'),
    )


class TaskList(BaseName):
    """Модель списка задач."""

    __table_args__ = (
        UniqueConstraint(
            'project_id', 'seq_number', name='uq_tasklist_id_seq_number'
        ),
    )
    seq_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TaskListStatus] = mapped_column(
        default=TaskListStatus.ACTIVE,
        server_default=TaskListStatus.ACTIVE.name,
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey('projects.id', ondelete='CASCADE')
    )
    project: Mapped['Project'] = relationship(
        'Project', back_populates='tasklists', lazy='joined'
    )
    tasks: Mapped[list['Task']] = relationship(
        'Task',
        back_populates='tasklist',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    __table_args__ = (
        # Ускоряет отрисовку Канбан-колонок внутри проекта
        Index('idx_tasklists_project_id', 'project_id'),
    )


# Промежуточная таблица для связи Task и Tag
task_tag = Table(
    'task_tag',
    Base.metadata,
    Column(
        'task_id',
        Integer,
        ForeignKey('tasks.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    Column(
        'tag_id',
        Integer,
        ForeignKey('tags.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    # Автоматически создаст уникальный составной индекс (task_id, tag_id)
    UniqueConstraint('task_id', 'tag_id', name='uq_task_tag_pair'),
    # Ручной индекс на второе поле (ускоряет выборки и удаление тегов)
    Index('idx_task_tag_tag_id', 'tag_id'),
)


# Промежуточная таблица для связи Task и Attachments
task_attachments = Table(
    'task_attachments',
    Base.metadata,
    Column(
        'task_id',
        Integer,
        ForeignKey('tasks.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    Column(
        'attachment_id',
        Integer,
        ForeignKey('attachments.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    # Автоматически создаст уникальный составной индекс
    # (task_id, attachment_id)
    UniqueConstraint(
        'task_id', 'attachment_id', name='uq_task_attachments_pair'
    ),
    # Ручной индекс на второе поле (ускоряет выборки и удаление файлов)
    Index('idx_task_attachments_attachment_id', 'attachment_id'),
)


class Task(BaseName, BaseCreated):
    """Модель задачи."""

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus]
    priority: Mapped[TaskPriority] = mapped_column(
        default=TaskPriority.LOW, server_default=TaskPriority.LOW.name
    )
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_periodic: Mapped[ReminderPeriodic | None] = mapped_column(
        nullable=True
    )
    tasklist_id: Mapped[int] = mapped_column(
        ForeignKey('tasklists.id', ondelete='CASCADE')
    )
    tasklist: Mapped['TaskList'] = relationship(
        'TaskList', back_populates='tasks', lazy='joined'
    )
    subtasks: Mapped[list['Subtask']] = relationship(
        'Subtask',
        back_populates='task',
        cascade='all, delete-orphan',
        lazy='selectin',
    )
    reminders: Mapped[list['Reminder']] = relationship(
        'Reminder',
        back_populates='task',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='Reminder.send_time.desc()',
    )
    tags: Mapped[list['Tag']] = relationship(
        secondary='task_tag',
        back_populates='tasks',
        lazy='selectin',
    )
    attachments: Mapped[list['Attachment']] = relationship(
        secondary='task_attachments',
        back_populates='tasks',
        lazy='selectin',
        cascade='delete',
    )

    __table_args__ = (
        # Золотой стандарт: ForeignKey на родительскую колонку
        Index('idx_tasks_tasklist_id', 'tasklist_id'),
        # Составной индекс для Celery Beat (send_deadline_coming_reminder /
        # send_overdue)
        Index('idx_tasks_status_deadline', 'status', 'deadline'),
        # Составной индекс для Celery Beat (send_start_task_reminder)
        Index('idx_tasks_status_start_at', 'status', 'start_at'),
    )


class Subtask(BaseName):
    """Модель подзадачи."""

    task_id: Mapped[int] = mapped_column(
        ForeignKey('tasks.id', ondelete='CASCADE')
    )
    status: Mapped[SubtaskStatus] = mapped_column(
        default=SubtaskStatus.IN_PROGRESS,
        server_default=SubtaskStatus.IN_PROGRESS.name,
    )
    task: Mapped['Task'] = relationship(
        'Task', back_populates='subtasks', lazy='joined'
    )

    __table_args__ = (
        # Ускоряет рендеринг подзадач внутри карточки задачи
        Index('idx_subtasks_task_id', 'task_id'),
    )


class Tag(BaseName):
    """Модель для хранения тега."""

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_tags_user_id_name'),
    )
    tasks: Mapped[list['Task']] = relationship(
        secondary='task_tag', back_populates='tags'
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
    )
    user: Mapped['User'] = relationship(
        'User',
        back_populates='tags',
    )

    __table_args__ = (
        # Ускоряет поиск тегов текущего пользователя (GET /tags/)
        Index('idx_tags_user_id', 'user_id'),
    )


class Attachment(Base):
    """Модель вложения с поддержкой MinIO."""

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int]
    minio_name: Mapped[str]
    mime_type: Mapped[MIMEType]
    tasks: Mapped[list['Task']] = relationship(
        secondary='task_attachments',
        back_populates='attachments',
    )
    __table_args__ = (
        CheckConstraint('size > 0', name='attachment_size_range'),
    )


class Reminder(Base):
    """Модель напоминания."""

    send_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel: Mapped[ReminderChannel] = mapped_column(
        default=ReminderChannel.EMAIL
    )
    status: Mapped[ReminderStatus] = mapped_column(
        default=ReminderStatus.QUEUED,
        server_default=ReminderStatus.QUEUED.name,
    )
    was_read: Mapped[bool] = mapped_column(default=False)
    task_id: Mapped[int] = mapped_column(
        ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False
    )
    task: Mapped['Task'] = relationship(
        'Task', back_populates='reminders', lazy='joined'
    )

    __table_args__ = (
        # Составной индекс для Celery Beat (send_reminder_task)
        Index('idx_reminders_status_send_time', 'status', 'send_time'),
        # Ускоряет оператор exists() защиты от спама писем в воркере
        Index('idx_reminders_task_id', 'task_id'),
    )
