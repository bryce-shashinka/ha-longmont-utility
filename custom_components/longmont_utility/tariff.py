"""Estimated Longmont Power & Communications residential (RE) electricity cost.

Source: https://longmontcolorado.gov/longmont-power-communications/powering-our-community/residential-rates/
Published prices already include the 8.64 percent franchise fee and no other
per-kWh rider applies to the standard RE schedule.

``RE_SCHEDULES`` is the built-in baseline. ``rates.py`` scrapes the City's page
daily and appends any changed schedule it observes, so new prices (the City
approved a further 6.88 percent increase for 2027) are picked up without a
release. Earlier entries stay for historical recalculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import IntervalReading

SUMMER_MONTHS = frozenset({6, 7, 8, 9})


@dataclass(frozen=True, slots=True)
class Tier:
    """Price for cycle consumption up to ``limit_kwh`` (``None`` is unbounded)."""

    limit_kwh: Decimal | None
    non_summer: Decimal
    summer: Decimal


@dataclass(frozen=True, slots=True)
class RateSchedule:
    """Rates in force from local date ``effective`` onward."""

    effective: date
    customer_charge: Decimal
    tiers: tuple[Tier, ...]


RE_SCHEDULES: tuple[RateSchedule, ...] = (
    RateSchedule(
        effective=date(2026, 1, 1),
        customer_charge=Decimal("17.50"),
        tiers=(
            Tier(Decimal(750), Decimal("0.1057"), Decimal("0.1164")),
            Tier(Decimal(1500), Decimal("0.1245"), Decimal("0.1373")),
            Tier(None, Decimal("0.1618"), Decimal("0.1783")),
        ),
    ),
)


def schedule_for(
    day: date, schedules: tuple[RateSchedule, ...] = RE_SCHEDULES
) -> RateSchedule:
    """Return the newest schedule effective on ``day`` (earliest as fallback)."""

    ordered = sorted(schedules, key=lambda item: item.effective)
    chosen = ordered[0]
    for schedule in ordered:
        if schedule.effective <= day:
            chosen = schedule
    return chosen


def cycle_last_day(cycle_start: date) -> date:
    """Return the final local date of a billing cycle (its read date)."""

    return next_cycle_start(cycle_start) - timedelta(days=1)


def is_summer(cycle_start: date) -> bool:
    """Apply the City's "bills read June-September" to a cycle.

    A cycle's bill is read on its last day, so a cycle is summer when that
    day falls in June through September (for a 19th start day: the cycles
    ending June 18 through September 18).
    """

    return cycle_last_day(cycle_start).month in SUMMER_MONTHS


def cycle_start_for(local_day: date, start_day: int) -> date:
    """Return the first local date of the billing cycle containing a date."""

    if not 1 <= start_day <= 28:
        raise ValueError("billing cycle start day must be between 1 and 28")
    if local_day.day >= start_day:
        return local_day.replace(day=start_day)
    previous = local_day.replace(day=1) - timedelta(days=1)
    return previous.replace(day=start_day)


def next_cycle_start(cycle_start: date) -> date:
    """Return the start of the following billing cycle."""

    if cycle_start.month == 12:
        return cycle_start.replace(year=cycle_start.year + 1, month=1)
    return cycle_start.replace(month=cycle_start.month + 1)


def _cycle_hours(cycle_start: date, zone: ZoneInfo) -> int:
    begin = datetime.combine(cycle_start, datetime.min.time(), zone)
    end = datetime.combine(next_cycle_start(cycle_start), datetime.min.time(), zone)
    return int((end.astimezone(UTC) - begin.astimezone(UTC)) // timedelta(hours=1))


def energy_cost(
    cycle_kwh_before: Decimal,
    energy_kwh: Decimal,
    schedule: RateSchedule,
    *,
    summer: bool,
) -> Decimal:
    """Price ``energy_kwh`` used after ``cycle_kwh_before``, split across tiers."""

    begin = cycle_kwh_before
    end = cycle_kwh_before + energy_kwh
    cost = Decimal()
    lower = Decimal()
    for tier in schedule.tiers:
        upper = end if tier.limit_kwh is None else tier.limit_kwh
        portion = min(end, upper) - max(begin, lower)
        if portion > 0:
            cost += portion * (tier.summer if summer else tier.non_summer)
        lower = upper
    return cost


def hourly_costs(
    readings: tuple[IntervalReading, ...],
    *,
    cycle_start_day: int,
    zone: ZoneInfo,
    schedules: tuple[RateSchedule, ...] = RE_SCHEDULES,
) -> list[tuple[datetime, Decimal]]:
    """Return (UTC hour start, estimated cost) for every hour with readings.

    Each hour carries its tiered energy charge plus the customer charge spread
    evenly over the actual hours of its billing cycle.
    """

    ordered = sorted(readings, key=lambda item: item.start.astimezone(UTC))
    hours: dict[datetime, Decimal] = {}
    current_cycle: date | None = None
    cycle_kwh = Decimal()
    charged_hours: set[datetime] = set()
    for reading in ordered:
        start = reading.start.astimezone(UTC)
        local_day = start.astimezone(zone).date()
        cycle = cycle_start_for(local_day, cycle_start_day)
        if cycle != current_cycle:
            current_cycle = cycle
            cycle_kwh = Decimal()
        schedule = schedule_for(local_day, schedules)
        cost = energy_cost(
            cycle_kwh, reading.energy_kwh, schedule, summer=is_summer(cycle)
        )
        cycle_kwh += reading.energy_kwh
        hour = start.replace(minute=0, second=0, microsecond=0)
        if hour not in charged_hours:
            charged_hours.add(hour)
            cost += schedule.customer_charge / _cycle_hours(cycle, zone)
        hours[hour] = hours.get(hour, Decimal()) + cost
    return sorted(hours.items())


@dataclass(frozen=True, slots=True)
class CurrentRate:
    """Marginal price at the current position in the billing cycle."""

    price: Decimal
    tier: int
    summer: bool
    cycle_start: date
    cycle_end: date
    cycle_kwh: Decimal
    schedule: RateSchedule


def current_rate(
    readings: tuple[IntervalReading, ...],
    today: date,
    *,
    cycle_start_day: int,
    zone: ZoneInfo,
    schedules: tuple[RateSchedule, ...] = RE_SCHEDULES,
) -> CurrentRate:
    """Return the price the next kWh in today's billing cycle would cost."""

    cycle = cycle_start_for(today, cycle_start_day)
    following = next_cycle_start(cycle)
    cycle_kwh = sum(
        (
            reading.energy_kwh
            for reading in readings
            if cycle <= reading.start.astimezone(zone).date() < following
        ),
        start=Decimal(),
    )
    schedule = schedule_for(today, schedules)
    summer = is_summer(cycle)
    tier_index = len(schedule.tiers) - 1
    for index, tier in enumerate(schedule.tiers):
        if tier.limit_kwh is None or cycle_kwh < tier.limit_kwh:
            tier_index = index
            break
    tier = schedule.tiers[tier_index]
    return CurrentRate(
        price=tier.summer if summer else tier.non_summer,
        tier=tier_index + 1,
        summer=summer,
        cycle_start=cycle,
        cycle_end=cycle_last_day(cycle),
        cycle_kwh=cycle_kwh,
        schedule=schedule,
    )
