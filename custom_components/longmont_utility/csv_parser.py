"""Normalize City of Longmont's malformed smart-meter CSV export."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .const import INTERVALS_PER_ORDINARY_DAY, TOTAL_TOLERANCE_KWH
from .models import IntervalReading, ParsedDay


class CsvValidationError(ValueError):
    """Raised when an export cannot be mapped to trustworthy intervals."""


def _parse_decimal(value: str, *, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as err:
        raise CsvValidationError(f"{field} must be numeric") from err
    if not parsed.is_finite():
        raise CsvValidationError(f"{field} must be finite")
    if parsed < 0:
        raise CsvValidationError(f"{field} must be non-negative")
    return parsed


def _interval_starts(reading_date: date, timezone: ZoneInfo) -> tuple[datetime, ...]:
    start = datetime.combine(reading_date, time.min, timezone)
    next_start = datetime.combine(reading_date + timedelta(days=1), time.min, timezone)
    if start.utcoffset() != next_start.utcoffset():
        raise CsvValidationError(
            "96 intervals cannot represent a daylight-saving transition date"
        )
    return tuple(start + timedelta(minutes=15 * index) for index in range(96))


def _is_portal_footer_note(row: list[str]) -> bool:
    """Return whether a malformed-width row is Cayenta's non-data footer."""

    populated = [field.strip() for field in row if field.strip()]
    return len(populated) == 1 and populated[0].startswith("* Note:")


def parse_smart_meter_csv(
    payload: str,
    timezone: ZoneInfo,
) -> tuple[ParsedDay, ...]:
    """Parse quarter-hour readings without trusting the incorrect CSV header."""

    rows = csv.reader(io.StringIO(payload, newline=""))
    try:
        next(rows)
    except StopIteration as err:
        raise CsvValidationError("CSV export is empty") from err

    parsed_days: list[ParsedDay] = []
    seen_dates: set[date] = set()
    for row_number, row in enumerate(rows, start=2):
        if not row or not any(field.strip() for field in row):
            continue
        if _is_portal_footer_note(row):
            continue
        if len(row) < INTERVALS_PER_ORDINARY_DAY + 2:
            raise CsvValidationError(
                f"row {row_number} must contain 96 interval values and a daily total"
            )
        if not row[INTERVALS_PER_ORDINARY_DAY + 1].strip():
            raise CsvValidationError(
                f"row {row_number} must contain 96 interval values"
            )
        if any(field.strip() for field in row[INTERVALS_PER_ORDINARY_DAY + 2 :]):
            raise CsvValidationError(f"row {row_number} contains unexpected data")

        try:
            reading_date = date.fromisoformat(row[0].strip())
        except ValueError as err:
            raise CsvValidationError(
                f"row {row_number} has an invalid reading date"
            ) from err
        if reading_date in seen_dates:
            raise CsvValidationError(f"row {row_number} has a duplicate reading date")

        interval_values = tuple(
            _parse_decimal(value.strip(), field=f"row {row_number} interval")
            for value in row[1 : INTERVALS_PER_ORDINARY_DAY + 1]
        )
        if len(interval_values) != INTERVALS_PER_ORDINARY_DAY:
            raise CsvValidationError(
                f"row {row_number} must contain 96 interval values"
            )
        total = _parse_decimal(
            row[INTERVALS_PER_ORDINARY_DAY + 1].strip(),
            field=f"row {row_number} daily total",
        )
        if abs(sum(interval_values, Decimal()) - total) > TOTAL_TOLERANCE_KWH:
            raise CsvValidationError(
                f"row {row_number} daily total does not match intervals"
            )

        starts = _interval_starts(reading_date, timezone)
        parsed_days.append(
            ParsedDay(
                reading_date=reading_date,
                intervals=tuple(
                    IntervalReading(start=start, energy_kwh=energy)
                    for start, energy in zip(starts, interval_values, strict=True)
                ),
                total_kwh=total,
            )
        )
        seen_dates.add(reading_date)

    if not parsed_days:
        raise CsvValidationError("CSV export contains no data rows")
    return tuple(sorted(parsed_days, key=lambda day: day.reading_date))
