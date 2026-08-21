from datetime import datetime

import pytest

from models.enums import ReminderPeriodic
from services.reminders import make_reminders_datetimes


@pytest.mark.asyncio
class TestMakeRemindersDatetimeUnit:
    """Юнит-тесты генератора цепочек дат напоминаний по ТЗ."""

    @pytest.mark.parametrize(
        'periodic, expected_count',
        [
            (ReminderPeriodic.NONE, 1),
            (ReminderPeriodic.DAILY, 6),
            (ReminderPeriodic.WEEKLY, 1),
            (ReminderPeriodic.WEEKDAYS, 5),
        ],
    )
    async def test_reminders_count(self, periodic, expected_count):
        """Тест: проверка базового количества созданных напоминаний."""
        task_dict = {
            'reminder_periodic': periodic,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 20, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        assert len(result) == expected_count

    async def test_none_periodic(self):
        """Тест: одиночное напоминание (периодичность отсутствует)."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.NONE,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 20, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        assert len(result) == 1
        assert result[0] == datetime(2024, 1, 15, 10, 0)

    async def test_daily_reminders(self):
        """Тест: ежедневные напоминания, включая дату дедлайна карточки."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.DAILY,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 18, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 1, 15, 10, 0),
            datetime(2024, 1, 16, 10, 0),
            datetime(2024, 1, 17, 10, 0),
            datetime(2024, 1, 18, 10, 0),
        ]
        assert result == expected

    async def test_weekly_reminders(self):
        """Тест: еженедельные напоминания на широком диапазоне дат."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.WEEKLY,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 29, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 1, 15, 10, 0),
            datetime(2024, 1, 22, 10, 0),
            datetime(2024, 1, 29, 10, 0),
        ]
        assert result == expected

    async def test_weekly_reminders_small_range(self):
        """Тест: еженедельные напоминания при дедлайне менее недели."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.WEEKLY,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 20, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [datetime(2024, 1, 15, 10, 0)]
        assert result == expected

    async def test_monthly_reminders_same_day(self):
        """Тест: ежемесячные напоминания с сохранением дня месяца."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.MONTHLY,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 3, 15, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 1, 15, 10, 0),
            datetime(2024, 2, 15, 10, 0),
            datetime(2024, 3, 15, 10, 0),
        ]
        assert result == expected

    async def test_monthly_reminders_last_day(self):
        """Тест: ежемесячные напоминания в конце месяца (високосный год)."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.MONTHLY,
            'reminder_datetime': datetime(2024, 1, 31, 10, 0),
            'deadline': datetime(2024, 3, 31, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 1, 31, 10, 0),
            datetime(2024, 2, 29, 10, 0),
            datetime(2024, 3, 29, 10, 0),
        ]
        assert result == expected

    async def test_monthly_reminders_cross_year(self):
        """Тест: ежемесячные напоминания на стыке смены лет."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.MONTHLY,
            'reminder_datetime': datetime(2024, 11, 30, 10, 0),
            'deadline': datetime(2025, 1, 31, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 11, 30, 10, 0),
            datetime(2024, 12, 30, 10, 0),
            datetime(2025, 1, 30, 10, 0),
        ]
        assert result == expected

    async def test_weekdays_reminders_skip_weekends(self):
        """Тест: напоминания строго по будням (выходные дни пропускаются)."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.WEEKDAYS,
            'reminder_datetime': datetime(2024, 1, 12, 10, 0),  # Пятница
            'deadline': datetime(2024, 1, 16, 10, 0),  # Вторник
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [
            datetime(2024, 1, 12, 10, 0),  # Пятница
            datetime(2024, 1, 15, 10, 0),  # Понедельник
            datetime(2024, 1, 16, 10, 0),  # Вторник
        ]
        assert result == expected

    async def test_weekdays_reminders_start_on_weekend(self):
        """Тест: старт в выходной переносится на ближайший будний день."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.WEEKDAYS,
            'reminder_datetime': datetime(2024, 1, 13, 10, 0),  # Суббота
            'deadline': datetime(2024, 1, 15, 10, 0),  # Понедельник
        }
        result = await make_reminders_datetimes(task_dict)
        expected = [datetime(2024, 1, 15, 10, 0)]
        assert result == expected

    async def test_start_after_deadline(self):
        """Тест: если дата старта позже дедлайна, цепочка пуста."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.DAILY,
            'reminder_datetime': datetime(2024, 1, 20, 10, 0),
            'deadline': datetime(2024, 1, 15, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        assert len(result) == 0

    async def test_boundary_condition_equal(self):
        """Тест: равенство старта и дедлайна создает 1 напоминание."""
        task_dict = {
            'reminder_periodic': ReminderPeriodic.DAILY,
            'reminder_datetime': datetime(2024, 1, 15, 10, 0),
            'deadline': datetime(2024, 1, 15, 10, 0),
        }
        result = await make_reminders_datetimes(task_dict)
        assert len(result) == 1
        assert result[0] == datetime(2024, 1, 15, 10, 0)
