"""Explicit ISO durations and timezone-aware deadlines, without guessed business days."""

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

PATTERN = re.compile(
    r"^P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d{1,6})?)S)?)?$"
)


@dataclass(frozen=True)
class Duration:
    years: int = 0
    months: int = 0
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: Decimal = Decimal(0)


def parse_duration(value: str) -> Duration:
    match = PATTERN.fullmatch(value) if len(value) <= 80 else None
    if not match or not any(match.groupdict().values()) or value.endswith("T"):
        raise ValueError("invalid ISO 8601 duration")
    groups = match.groupdict()
    if groups["weeks"] and any(groups[x] for x in groups if x != "weeks"):
        raise ValueError("week durations cannot mix other components")
    result = Duration(
        years=int(groups["years"] or 0),
        months=int(groups["months"] or 0),
        weeks=int(groups["weeks"] or 0),
        days=int(groups["days"] or 0),
        hours=int(groups["hours"] or 0),
        minutes=int(groups["minutes"] or 0),
        seconds=Decimal(groups["seconds"] or 0),
    )
    if result == Duration():
        raise ValueError("duration must be positive")
    if (
        result.years > 100
        or result.months > 1200
        or result.weeks > 5200
        or result.days > 36600
        or result.hours > 878400
        or result.minutes > 52704000
        or result.seconds > 3162240000
    ):
        raise ValueError("duration exceeds v1 bound of approximately 100 years")
    return result


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(UTC)


def add_duration(start: datetime, duration: Duration, timezone: str) -> datetime:
    local = aware(start).astimezone(ZoneInfo(timezone))
    month_index = (local.year + duration.years) * 12 + local.month - 1 + duration.months
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    if not 1 <= year <= 9999:
        raise ValueError("deadline is outside supported timestamp range")
    shifted = local.replace(
        year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1])
    )
    shifted += timedelta(weeks=duration.weeks, days=duration.days)
    # Calendar date additions preserve wall-clock local date; reject DST gaps.
    if shifted.astimezone(UTC).astimezone(ZoneInfo(timezone)).replace(
        tzinfo=None
    ) != shifted.replace(tzinfo=None):
        raise ValueError("calendar deadline lands in a DST gap; human review required")
    if any((duration.years, duration.months, duration.weeks, duration.days)):
        alternative = shifted.replace(fold=1 - shifted.fold)
        if alternative.utcoffset() != shifted.utcoffset():
            raise ValueError(
                "calendar deadline lands in an ambiguous DST time; human review required"
            )
    return shifted.astimezone(UTC) + timedelta(
        hours=duration.hours, minutes=duration.minutes, microseconds=int(duration.seconds * 1000000)
    )


@dataclass(frozen=True)
class DeadlineResult:
    due_at: datetime | None
    state: str
    notice: str | None = None


def calculate_deadline(
    *,
    start: datetime | None,
    duration: str | None,
    now: datetime,
    timezone: str,
    calendar_type: str = "calendar",
) -> DeadlineResult:
    current = aware(now)
    ZoneInfo(timezone)
    if calendar_type == "business":
        return DeadlineResult(None, "unsupported_in_v1", "business_calendar_requires_human_review")
    if calendar_type != "calendar":
        raise ValueError("unknown calendar")
    if duration is None:
        return DeadlineResult(None, "not_applicable", "no_numeric_deadline_in_source")
    parsed = parse_duration(duration)
    if start is None:
        return DeadlineResult(None, "not_applicable", "start_event_missing")
    anchor = aware(start)
    if anchor > current:
        raise ValueError("start event cannot be in the future")
    due = add_duration(anchor, parsed, timezone)
    remaining = (due - current).total_seconds()
    window = (due - anchor).total_seconds()
    if remaining < 0:
        state = "overdue"
    elif remaining <= window * 0.25 or remaining < 3600:
        state = "due_soon"
    else:
        state = "upcoming"
    return DeadlineResult(due, state)


def minutes_since_payment(timestamp: datetime, now: datetime) -> int:
    difference = (aware(now) - aware(timestamp)).total_seconds()
    if difference < 0:
        raise ValueError("payment timestamp is in the future")
    return int(difference // 60)
