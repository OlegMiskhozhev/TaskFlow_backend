from enum import StrEnum


class UserRole(StrEnum):
    """Роли пользователя."""

    ADMIN = 'Администратор'
    GUEST = 'Гость'
    USER = 'Пользователь'


class ProjectStatus(StrEnum):
    """Статусы проекта."""

    IN_PROGRESS = 'В работе'
    ON_PAUSE = 'Приостановлен'
    DONE = 'Завершен'
    ARCHIVE = 'Архивный'


class TaskListStatus(StrEnum):
    """Статусы списка задач."""

    ACTIVE = 'Активный'
    DONE = 'Сделано'


class TaskStatus(StrEnum):
    """Статусы задачи."""

    IN_PROGRESS = 'in_progress'
    SCHEDULE = 'schedule'
    DONE = 'done'


class SubtaskStatus(StrEnum):
    """Статусы подзадачи."""

    IN_PROGRESS = 'В работе'
    DONE = 'Завершено'


class TaskPriority(StrEnum):
    """Приоритеты задачи."""

    HIGH = 'Высокий'
    MID = 'Средний'
    LOW = 'Низкий'


class AvatarMIMEType(StrEnum):
    """Разрешенные типы файлов для MIME."""

    PNG = 'png'
    JPEG = 'jpeg'
    JPG = 'jpg'


class MIMEType(StrEnum):
    """Разрешенные типы файлов для MIME."""

    PNG = 'png'
    JPEG = 'jpeg'
    JPG = 'jpg'
    TXT = 'txt'
    DOC = 'doc'
    DOCX = 'docx'
    XLS = 'xls'
    XLSX = 'xlsx'


class ReminderChannel(StrEnum):
    """Каналы отправки напоминаний."""

    EMAIL = 'email'
    WEBPUSH = 'webpush'


class ReminderStatus(StrEnum):
    """Статусы напоминаний."""

    QUEUED = 'queued'
    SENT = 'sent'


class ReminderPeriodic(StrEnum):
    """Переодичность напоминаний."""

    NONE = 'Нет'
    DAILY = 'Ежедневно'
    WEEKLY = 'Еженедельно'
    MONTHLY = 'Ежемесячно'
    WEEKDAYS = 'Пн-Пт'


class Timezone(StrEnum):
    """Часовые пояса"""

    MIDWAY = 'Pacific/Midway'
    TAHITI = 'Pacific/Tahiti'
    GAMBIER = 'Pacific/Gambier'
    ANCHORAGE = 'America/Anchorage'
    LOS_ANGELES = 'America/Los_Angeles'
    MEXICO_CITY = 'America/Mexico_City'
    JAMAICA = 'America/Jamaica'
    NEW_YORK = 'America/New_York'
    SAO_PAULO = 'America/Sao_Paulo'
    SOUTH_GEORGIA = 'Atlantic/South_Georgia'
    CAPE_VERDE = 'Atlantic/Cape_Verde'
    UTC = 'UTC'
    LONDON = 'Europe/London'
    PARIS = 'Europe/Paris'
    MOSCOW = 'Europe/Moscow'
    DUBAI = 'Asia/Dubai'
    ALMATY = 'Asia/Almaty'
    OMSK = 'Asia/Omsk'
    BANGKOK = 'Asia/Bangkok'
    HONG_KONG = 'Asia/Hong_Kong'
    TOKYO = 'Asia/Tokyo'
    SYDNEY = 'Australia/Sydney'
    SAKHALIN = 'Asia/Sakhalin'
    FIJI = 'Pacific/Fiji'
