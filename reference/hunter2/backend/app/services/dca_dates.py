"""Deterministic contribution schedule generation."""

from calendar import monthrange
from datetime import date, timedelta

from backend.app.models.dca import DCAFrequency


def generate_dca_dates(
    start_date: date, end_date: date, frequency: DCAFrequency
) -> tuple[date, ...]:
    """Return inclusive scheduled dates for a DCA strategy.

    Monthly dates remain anchored to the original day. When that day does not
    exist, the month's last day is used without causing drift in later months.
    """

    if end_date < start_date:
        raise ValueError("end_date cannot be before start_date")
    if not isinstance(frequency, DCAFrequency):
        raise ValueError(f"Unsupported DCA frequency: {frequency!r}")

    if frequency is DCAFrequency.DAILY:
        return _fixed_interval_dates(start_date, end_date, days=1)
    if frequency is DCAFrequency.WEEKLY:
        return _fixed_interval_dates(start_date, end_date, days=7)
    return _monthly_dates(start_date, end_date)


def _fixed_interval_dates(start_date: date, end_date: date, *, days: int) -> tuple[date, ...]:
    dates: list[date] = []
    current = start_date
    step = timedelta(days=days)
    while current <= end_date:
        dates.append(current)
        current += step
    return tuple(dates)


def _monthly_dates(start_date: date, end_date: date) -> tuple[date, ...]:
    dates: list[date] = []
    month_offset = 0
    while True:
        absolute_month = start_date.year * 12 + start_date.month - 1 + month_offset
        year, zero_based_month = divmod(absolute_month, 12)
        month = zero_based_month + 1
        day = min(start_date.day, monthrange(year, month)[1])
        scheduled_date = date(year, month, day)
        if scheduled_date > end_date:
            break
        dates.append(scheduled_date)
        month_offset += 1
    return tuple(dates)

