from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from custom_components.longmont_utility.models import IntervalReading
from custom_components.longmont_utility.statistics import build_hourly_cost_samples
from custom_components.longmont_utility.tariff import (
    RE_SCHEDULES,
    cycle_last_day,
    cycle_start_for,
    energy_cost,
    hourly_costs,
    is_summer,
    next_cycle_start,
)

DENVER = ZoneInfo("America/Denver")
SCHEDULE = RE_SCHEDULES[0]


def quarter_hours(
    first_local: datetime, count: int, kwh: str
) -> tuple[IntervalReading, ...]:
    start = first_local.astimezone(UTC)
    return tuple(
        IntervalReading(start + timedelta(minutes=15 * index), Decimal(kwh))
        for index in range(count)
    )


def test_tier_one_only() -> None:
    assert energy_cost(Decimal(0), Decimal(10), SCHEDULE, summer=False) == Decimal(
        "1.0570"
    )


def test_split_across_750_boundary() -> None:
    cost = energy_cost(Decimal(745), Decimal(10), SCHEDULE, summer=True)

    assert cost == Decimal(5) * Decimal("0.1164") + Decimal(5) * Decimal("0.1373")


def test_split_across_both_boundaries() -> None:
    cost = energy_cost(Decimal(700), Decimal(900), SCHEDULE, summer=False)

    assert cost == (
        Decimal(50) * Decimal("0.1057")
        + Decimal(750) * Decimal("0.1245")
        + Decimal(100) * Decimal("0.1618")
    )


def test_tier_three_only() -> None:
    assert energy_cost(Decimal(2000), Decimal(1), SCHEDULE, summer=True) == Decimal(
        "0.1783"
    )


@pytest.mark.parametrize(
    ("day", "start_day", "expected"),
    [
        (date(2026, 9, 14), 1, date(2026, 9, 1)),
        (date(2026, 9, 14), 15, date(2026, 8, 15)),
        (date(2026, 9, 15), 15, date(2026, 9, 15)),
        (date(2026, 1, 3), 20, date(2025, 12, 20)),
    ],
)
def test_cycle_start(day: date, start_day: int, expected: date) -> None:
    assert cycle_start_for(day, start_day) == expected


def test_cycle_start_day_validated() -> None:
    with pytest.raises(ValueError):
        cycle_start_for(date(2026, 9, 1), 29)


def test_next_cycle_wraps_year() -> None:
    assert next_cycle_start(date(2026, 12, 20)) == date(2027, 1, 20)


def test_season_follows_cycle_read_date_for_calendar_cycles() -> None:
    assert not is_summer(date(2026, 5, 1))
    assert is_summer(date(2026, 6, 1))
    assert is_summer(date(2026, 9, 1))
    assert not is_summer(date(2026, 10, 1))


def test_season_follows_cycle_read_date_for_19th_cycles() -> None:
    # Bill "08/19/26 to 09/18/26" is read in September: summer.
    assert not is_summer(date(2026, 4, 19))  # read May 18
    assert is_summer(date(2026, 5, 19))  # read June 18
    assert is_summer(date(2026, 8, 19))  # read September 18
    assert not is_summer(date(2026, 9, 19))  # read October 18


def test_cycle_last_day() -> None:
    assert cycle_last_day(date(2026, 8, 19)) == date(2026, 9, 18)
    assert cycle_last_day(date(2026, 12, 1)) == date(2026, 12, 31)


def test_customer_charge_sums_to_one_cycle_across_dst() -> None:
    # Cycle 2026-10-15 .. 2026-11-15 contains the November DST change.
    first = datetime(2026, 10, 15, tzinfo=DENVER)
    end = datetime(2026, 11, 15, tzinfo=DENVER)
    count = int((end.astimezone(UTC) - first.astimezone(UTC)) / timedelta(minutes=15))
    readings = quarter_hours(first, count, "0")

    costs = hourly_costs(readings, cycle_start_day=15, zone=DENVER)

    assert len(costs) == count // 4
    assert sum((cost for _, cost in costs), Decimal()).quantize(
        Decimal("0.0001")
    ) == Decimal("17.5000")


def test_tier_resets_at_cycle_boundary() -> None:
    # 800 kWh in the last hour of one cycle, then 1 kWh at the start of the next.
    before = quarter_hours(datetime(2026, 11, 14, 23, tzinfo=DENVER), 4, "200")
    after = quarter_hours(datetime(2026, 11, 15, 0, tzinfo=DENVER), 4, "0.25")

    costs = dict(hourly_costs(before + after, cycle_start_day=15, zone=DENVER))
    first_hour = datetime(2026, 11, 14, 23, tzinfo=DENVER).astimezone(UTC)
    second_hour = datetime(2026, 11, 15, 0, tzinfo=DENVER).astimezone(UTC)
    oct_hours = 31 * 24 + 1  # Oct 15 - Nov 15 includes the 25-hour DST day
    nov_hours = 30 * 24

    assert costs[first_hour] == (
        Decimal(750) * Decimal("0.1057")
        + Decimal(50) * Decimal("0.1245")
        + Decimal("17.50") / oct_hours
    )
    assert costs[second_hour] == Decimal("0.1057") + Decimal("17.50") / nov_hours


def test_cost_samples_are_cumulative() -> None:
    readings = quarter_hours(datetime(2026, 9, 1, tzinfo=DENVER), 8, "0.5")

    samples = build_hourly_cost_samples(readings, cycle_start_day=1, zone=DENVER)

    assert len(samples) == 2
    assert samples[1].sum == pytest.approx(samples[0].state + samples[1].state)
    hourly_fixed = 17.50 / (30 * 24)
    assert samples[0].state == pytest.approx(2 * 0.1164 + hourly_fixed)
