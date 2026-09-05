"""Domain models for Longmont smart-meter consumption."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IntervalReading:
    """Energy consumed during the quarter hour beginning at ``start``."""

    start: datetime
    energy_kwh: Decimal


@dataclass(frozen=True, slots=True)
class ParsedDay:
    """Validated interval consumption for one local reading date."""

    reading_date: date
    intervals: tuple[IntervalReading, ...]
    total_kwh: Decimal

