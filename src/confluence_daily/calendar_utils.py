from __future__ import annotations

import calendar
from datetime import date, timedelta


KOREAN_WEEKDAYS = (
    "\uc6d4",
    "\ud654",
    "\uc218",
    "\ubaa9",
    "\uae08",
    "\ud1a0",
    "\uc77c",
)


def month_page_title(user_name: str, target_date: date) -> str:
    return f"{user_name}_{target_date.year}\ub144 {target_date.month}\uc6d4"


def report_month_for_date(work_date: date, policy: str = "workweek_end_month") -> date:
    if policy == "date_month":
        return date(work_date.year, work_date.month, 1)
    if policy != "workweek_end_month":
        raise ValueError(f"Unknown month page policy: {policy}")
    if work_date.weekday() >= 5:
        raise ValueError("Daily rows are only defined for Monday-Friday.")

    monday = work_date - timedelta(days=work_date.weekday())
    friday = monday + timedelta(days=4)
    return date(friday.year, friday.month, 1)


def first_workweek_monday(year: int, month: int) -> date:
    first = date(year, month, 1)
    monday = first - timedelta(days=first.weekday())

    has_month_workday = any(
        (monday + timedelta(days=offset)).month == month
        for offset in range(5)
    )
    if not has_month_workday:
        monday += timedelta(days=7)
    return monday


def last_month_workday(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    current = date(year, month, last_day)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def week_number_for_date(work_date: date, target_year: int | None = None, target_month: int | None = None) -> int:
    if work_date.weekday() >= 5:
        raise ValueError("Daily rows are only defined for Monday-Friday.")

    year = target_year or work_date.year
    month = target_month or work_date.month
    start = first_workweek_monday(year, month)
    if work_date < start:
        raise ValueError(f"{work_date.isoformat()} is before the first workweek.")
    return ((work_date - start).days // 7) + 1


def row_index_for_date(work_date: date) -> int:
    if work_date.weekday() >= 5:
        raise ValueError("Daily rows are only defined for Monday-Friday.")
    return work_date.weekday()


def weeks_in_month(year: int, month: int, minimum: int = 4) -> int:
    last_workday = last_month_workday(year, month)
    return max(minimum, week_number_for_date(last_workday, year, month))


def dates_for_week(year: int, month: int, week_number: int) -> tuple[date | None, ...]:
    monday = first_workweek_monday(year, month) + timedelta(days=(week_number - 1) * 7)
    days: list[date | None] = []
    for offset in range(5):
        current = monday + timedelta(days=offset)
        days.append(current if current.month == month else None)
    return tuple(days)


def format_date_label(work_date: date) -> str:
    weekday = KOREAN_WEEKDAYS[work_date.weekday()]
    return f"{work_date.month}/{work_date.day}({weekday})"
