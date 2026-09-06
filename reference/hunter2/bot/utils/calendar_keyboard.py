"""Reusable Telegram keyboards and callbacks for calendar-date selection."""

from __future__ import annotations

from calendar import Calendar, month_name, monthrange
from dataclasses import dataclass
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

PERIOD_PRESETS = (
    "1 Year",
    "3 Years",
    "5 Years",
    "10 Years",
    "Since 2020",
    "Max Available",
)
CUSTOM_DATES = "ðŸ“… Custom Dates"
CALENDAR_DATA_KEY = "calendar"


@dataclass(frozen=True, slots=True)
class CalendarAction:
    action: str
    values: tuple[int, ...] = ()
    selected_date: date | None = None


def build_period_keyboard() -> ReplyKeyboardMarkup:
    rows = [PERIOD_PRESETS[index : index + 2] for index in range(0, 6, 2)]
    rows.append((CUSTOM_DATES, "âŒ Cancel"))
    return ReplyKeyboardMarkup(tuple(rows), resize_keyboard=True, one_time_keyboard=True)


def build_month_calendar(year: int, month: int, *, max_date: date) -> InlineKeyboardMarkup:
    """Build Monday-first day grid; future days have inert callback data."""

    _validate_month(year, month)
    previous_year, previous_month = adjacent_month(year, month, -1)
    next_year, next_month = adjacent_month(year, month, 1)
    previous_callback = (
        f"cal:prev:{year}:{month}" if previous_year >= 1 else "cal:noop"
    )
    next_callback = (
        f"cal:next:{year}:{month}"
        if (next_year, next_month) <= (max_date.year, max_date.month)
        else "cal:noop"
    )
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(f"{month_name[month]} {year}", callback_data=f"cal:years:{year}")],
        [
            InlineKeyboardButton("â€¹", callback_data=previous_callback),
            InlineKeyboardButton("Choose month", callback_data=f"cal:months:{year}"),
            InlineKeyboardButton("â€º", callback_data=next_callback),
        ],
        [
            InlineKeyboardButton(day, callback_data="cal:noop")
            for day in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
        ],
    ]
    for week in Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:noop"))
                continue
            value = date(year, month, day)
            callback = f"cal:day:{value.isoformat()}" if value <= max_date else "cal:noop"
            row.append(InlineKeyboardButton(str(day), callback_data=callback))
        rows.append(row)
    rows.append(_footer())
    return InlineKeyboardMarkup(rows)


def build_year_picker(anchor_year: int, *, max_date: date) -> InlineKeyboardMarkup:
    newest = max(1, min(anchor_year, max_date.year))
    years = list(range(newest, max(0, newest - 8), -1))
    rows = [
        [InlineKeyboardButton("Choose year", callback_data="cal:noop")],
        *[
            [InlineKeyboardButton(str(year), callback_data=f"cal:year:{year}")]
            for year in years
        ],
        [
            InlineKeyboardButton(
                "Â« Older",
                callback_data=(
                    f"cal:older:{years[-1] - 1}" if years[-1] > 1 else "cal:noop"
                ),
            ),
            InlineKeyboardButton("Newer Â»", callback_data=f"cal:newer:{years[0] + 8}"),
        ],
        _footer(),
    ]
    return InlineKeyboardMarkup(rows)


def build_month_picker(year: int, *, max_date: date) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(1, 13, 3):
        row = []
        for month in range(start, start + 3):
            enabled = (year, month) <= (max_date.year, max_date.month)
            callback = f"cal:month:{year}:{month}" if enabled else "cal:noop"
            row.append(InlineKeyboardButton(month_name[month][:3], callback_data=callback))
        rows.append(row)
    rows.append([InlineKeyboardButton("Choose year", callback_data=f"cal:years:{year}")])
    rows.append(_footer())
    return InlineKeyboardMarkup(rows)


def parse_calendar_callback(data: str) -> CalendarAction:
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "cal":
        raise ValueError("invalid calendar callback")
    action = parts[1]
    if action == "day" and len(parts) == 3:
        return CalendarAction(action, selected_date=date.fromisoformat(parts[2]))
    if action in {"year", "years", "months", "older", "newer"} and len(parts) == 3:
        return CalendarAction(action, (int(parts[2]),))
    if action in {"month", "prev", "next"} and len(parts) == 4:
        return CalendarAction(action, (int(parts[2]), int(parts[3])))
    if action in {"back", "cancel", "noop"} and len(parts) == 2:
        return CalendarAction(action)
    raise ValueError("invalid calendar callback")


def adjacent_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + month - 1 + offset
    new_year, zero_month = divmod(absolute, 12)
    return new_year, zero_month + 1


def preset_date_range(label: str, *, today: date) -> tuple[date, date]:
    years = {"1 Year": 1, "3 Years": 3, "5 Years": 5, "10 Years": 10}
    if label in years:
        year = today.year - years[label]
        day = min(today.day, monthrange(year, today.month)[1])
        return date(year, today.month, day), today
    if label == "Since 2020":
        return date(2020, 1, 1), today
    if label == "Max Available":
        # Common yfinance coverage for every centrally supported asset begins
        # by 2015; asset/provider availability is still validated downstream.
        return date(2015, 1, 1), today
    raise ValueError("unsupported period preset")


def _footer() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton("â¬…ï¸ Back", callback_data="cal:back"),
        InlineKeyboardButton("âŒ Cancel", callback_data="cal:cancel"),
    ]


def _validate_month(year: int, month: int) -> None:
    if year < 1 or not 1 <= month <= 12:
        raise ValueError("invalid calendar month")
