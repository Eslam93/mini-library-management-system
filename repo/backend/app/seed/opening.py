"""When the library is open and who is at the desk. Every registration, borrow and return in the
generated history happens during opening hours and names the member of staff on duty.
"""

import random
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta

# (opening hour, closing hour), in UTC.
WEEKDAY_HOURS = (9, 19)
SATURDAY_HOURS = (10, 16)
SATURDAY, SUNDAY = 5, 6
# Closed on Sundays and on these (month, day) holidays.
HOLIDAYS = frozenset({(1, 1), (12, 25), (12, 26)})
# The desk shift changes at this hour.
SHIFT_CHANGE_HOUR = 14
# Nobody is served in the last minutes before closing.
LAST_SERVICE = timedelta(minutes=15)

ONE_DAY = timedelta(days=1)


def is_open(day: date) -> bool:
    return day.weekday() != SUNDAY and (day.month, day.day) not in HOLIDAYS


def opening_hours(day: date) -> tuple[int, int]:
    return SATURDAY_HOURS if day.weekday() == SATURDAY else WEEKDAY_HOURS


def next_open_day(day: date) -> date:
    """The day itself when the library is open, otherwise the next day it is."""
    while not is_open(day):
        day += ONE_DAY
    return day


def previous_open_day(day: date) -> date:
    """The day itself when the library is open, otherwise the last day before it that was."""
    while not is_open(day):
        day -= ONE_DAY
    return day


def open_days(first: date, last: date) -> list[date]:
    """The opening days from first to last, both included."""
    days = []
    day = first
    while day <= last:
        if is_open(day):
            days.append(day)
        day += ONE_DAY
    return days


def moment_on(rng: random.Random, day: date, hours: tuple[int, int] | None = None) -> datetime:
    """A random second during the day's opening hours, within the preferred hours when they
    overlap them.
    """
    opens, closes = opening_hours(day)
    if hours is not None and max(opens, hours[0]) < min(closes, hours[1]):
        opens, closes = max(opens, hours[0]), min(closes, hours[1])
    latest = closes * 3600 - int(LAST_SERVICE.total_seconds())
    second = rng.randrange(opens * 3600, latest)
    return datetime.combine(day, time(tzinfo=UTC)) + timedelta(seconds=second)


def staff_on_duty(moment: datetime, staff: Sequence[str]) -> str:
    """The rota: two shifts a day, and the week's pattern moves on by one person every week."""
    shift = 0 if moment.hour < SHIFT_CHANGE_HOUR else 1
    week = moment.date().toordinal() // 7
    return staff[(week + 2 * moment.weekday() + shift) % len(staff)]
