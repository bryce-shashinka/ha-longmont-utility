from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.longmont_utility.models import IntervalReading
from custom_components.longmont_utility.rates import (
    FAILURES_BEFORE_REPAIR,
    RateParseError,
    RateTracker,
    parse_residential_rates,
    schedule_from_dict,
    schedule_to_dict,
)
from custom_components.longmont_utility.tariff import (
    RE_SCHEDULES,
    RateSchedule,
    Tier,
    current_rate,
    hourly_costs,
    schedule_for,
)

FIXTURE = Path(__file__).with_name("fixtures") / "residential_rates.html"
DENVER = ZoneInfo("America/Denver")
SEEN = date(2026, 10, 13)
NOW = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def page() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def raised(schedule: RateSchedule, effective: date) -> RateSchedule:
    return RateSchedule(
        effective=effective,
        customer_charge=schedule.customer_charge + Decimal(1),
        tiers=tuple(
            Tier(
                tier.limit_kwh,
                tier.non_summer + Decimal("0.01"),
                tier.summer + Decimal("0.01"),
            )
            for tier in schedule.tiers
        ),
    )


def table_html(rows: list[tuple[str, str, str, str, str]]) -> str:
    cells = "".join(
        "<tr>" + "".join(f"<td><p>{cell}</p></td>" for cell in row) + "</tr>"
        for row in rows
    )
    header = (
        "<tr><td>Customer Tier</td><td>Energy Usage</td><td>Non-Summer Rate</td>"
        "<td>Summer Rate</td><td>Customer Charge</td></tr>"
    )
    return f"<html><body><table>{header}{cells}</table></body></html>"


GOOD_ROWS = [
    ("Tier 1", "Up to 750 kWh", "10.57¢ per kWh", "11.64¢ per kWh", "$17.50"),
    ("Tier 2", "751 &#8211; 1,500 kWh", "12.45¢ per kWh", "13.73¢ per kWh", "$17.50"),
    ("Tier 3", "1,501 or more kWh", "16.18¢ per kWh", "17.83¢ per kWh", "$17.50"),
]


class MemoryStore:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = data


def fetcher(*pages: str | Exception):
    queue = list(pages)
    calls: list[int] = []

    async def fetch() -> str:
        calls.append(1)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return fetch, calls


def test_live_page_fixture_parses_to_builtin_prices() -> None:
    schedule, stated = parse_residential_rates(page(), first_seen=SEEN)

    assert not stated
    assert schedule.effective == SEEN
    assert schedule.customer_charge == Decimal("17.50")
    assert schedule.tiers == RE_SCHEDULES[-1].tiers


def test_stated_effective_date_is_used() -> None:
    html = table_html(GOOD_ROWS).replace(
        "<body>", "<body><p>Rates effective January 1, 2027.</p>"
    )

    schedule, stated = parse_residential_rates(html, first_seen=SEEN)

    assert stated
    assert schedule.effective == date(2027, 1, 1)


def test_numeric_effective_date_is_used() -> None:
    html = table_html(GOOD_ROWS).replace("<body>", "<body>Effective: 1/1/2027")

    assert parse_residential_rates(html, first_seen=SEEN)[0].effective == date(
        2027, 1, 1
    )


def test_cost_effective_prose_is_not_a_date() -> None:
    html = table_html(GOOD_ROWS).replace(
        "<body>", "<body>The RD rate may be more cost effective for 2026 homes."
    )

    assert parse_residential_rates(html, first_seen=SEEN)[0].effective == SEEN


@pytest.mark.parametrize(
    "rows",
    [
        GOOD_ROWS[:2],
        [*GOOD_ROWS, ("Tier 4", "3,001 or more kWh", "20¢", "21¢", "$17.50")],
        [
            GOOD_ROWS[0],
            ("Tier 2", "751 - 700 kWh", "12.45¢", "13.73¢", "$17.50"),
            GOOD_ROWS[2],
        ],
        [
            GOOD_ROWS[0],
            ("Tier 2", "751 - 1,500 kWh", "9.00¢", "13.73¢", "$17.50"),
            GOOD_ROWS[2],
        ],
        [
            GOOD_ROWS[0],
            ("Tier 2", "751 - 1,500 kWh", "13.80¢", "13.73¢", "$17.50"),
            GOOD_ROWS[2],
        ],
        [
            GOOD_ROWS[0],
            GOOD_ROWS[1],
            ("Tier 3", "1,501 or more kWh", "16.18¢", "70.00¢", "$17.50"),
        ],
        [("Tier 1", "Up to 750 kWh", "1.57¢", "11.64¢", "$17.50"), *GOOD_ROWS[1:]],
        [(r[0], r[1], r[2], r[3], "$170.00") for r in GOOD_ROWS],
        [GOOD_ROWS[0], GOOD_ROWS[1], (*GOOD_ROWS[2][:4], "$18.00")],
        [
            GOOD_ROWS[0],
            GOOD_ROWS[1],
            ("Tier 3", "1,501 - 3,000 kWh", "16.18¢", "17.83¢", "$17.50"),
        ],
        [
            GOOD_ROWS[0],
            ("Tier 2", "751 - 1,500 kWh", "$0.1245", "13.73¢", "$17.50"),
            GOOD_ROWS[2],
        ],
    ],
    ids=[
        "two-tiers",
        "four-tiers",
        "boundary-decreases",
        "price-decreases",
        "summer-below-non-summer",
        "price-too-high",
        "price-too-low",
        "charge-too-high",
        "charge-differs",
        "last-tier-bounded",
        "price-not-cents",
    ],
)
def test_invalid_tables_are_rejected(rows: list[tuple[str, ...]]) -> None:
    with pytest.raises(RateParseError):
        parse_residential_rates(table_html(rows), first_seen=SEEN)  # type: ignore[arg-type]


def test_missing_table_is_rejected() -> None:
    with pytest.raises(RateParseError):
        parse_residential_rates(
            "<html><table><tr><td>x</td></tr></table></html>", first_seen=SEEN
        )


def test_schedule_round_trips_through_storage() -> None:
    schedule = raised(RE_SCHEDULES[0], date(2027, 1, 1))

    assert schedule_from_dict(schedule_to_dict(schedule)) == schedule


def test_unchanged_page_records_check_without_observation() -> None:
    store = MemoryStore()
    fetch, _ = fetcher(page())
    tracker = RateTracker(store, fetch)

    result = asyncio.run(tracker.async_check(SEEN, NOW))

    assert result.attempted and result.changed is None and result.error is None
    assert tracker.source == "built-in"
    assert tracker.last_checked == NOW
    assert store.data is not None and store.data["observations"] == []


def test_checks_at_most_once_per_day() -> None:
    fetch, calls = fetcher(page(), page())
    tracker = RateTracker(MemoryStore(), fetch)

    asyncio.run(tracker.async_check(SEEN, NOW))
    second = asyncio.run(tracker.async_check(SEEN, NOW + timedelta(hours=5)))

    assert not second.attempted
    assert len(calls) == 1


def test_changed_prices_append_dated_observation() -> None:
    new = raised(RE_SCHEDULES[0], SEEN)
    html = table_html(
        [
            ("Tier 1", "Up to 750 kWh", "11.57¢", "12.64¢", "$18.50"),
            ("Tier 2", "751 - 1,500 kWh", "13.45¢", "14.73¢", "$18.50"),
            ("Tier 3", "1,501 or more kWh", "17.18¢", "18.83¢", "$18.50"),
        ]
    )
    store = MemoryStore()
    fetch, _ = fetcher(html, html)
    tracker = RateTracker(store, fetch)

    result = asyncio.run(tracker.async_check(SEEN, NOW))
    again = asyncio.run(tracker.async_check(SEEN + timedelta(days=1), NOW))

    assert result.changed == new
    assert again.changed is None
    assert tracker.source == "scraped"
    assert tracker.schedules == (*RE_SCHEDULES, new)
    reloaded = RateTracker(MemoryStore(store.data), fetcher()[0])
    asyncio.run(reloaded.async_load())
    assert reloaded.schedules == (*RE_SCHEDULES, new)


def test_failures_accumulate_daily_and_reset_on_success() -> None:
    errors: list[str | Exception] = [TimeoutError()] * FAILURES_BEFORE_REPAIR
    fetch, _ = fetcher(*errors, "<html>no table</html>", page())
    tracker = RateTracker(MemoryStore(), fetch)

    for offset in range(FAILURES_BEFORE_REPAIR + 1):
        result = asyncio.run(tracker.async_check(SEEN + timedelta(days=offset), NOW))
        assert result.error is not None
    assert tracker.consecutive_failures == FAILURES_BEFORE_REPAIR + 1
    assert tracker.last_checked is None

    ok = asyncio.run(
        tracker.async_check(SEEN + timedelta(days=FAILURES_BEFORE_REPAIR + 1), NOW)
    )
    assert ok.error is None
    assert tracker.consecutive_failures == 0


def test_newest_effective_schedule_wins_and_observation_wins_ties() -> None:
    base = RE_SCHEDULES[0]
    later = raised(base, date(2027, 1, 1))
    same_day = raised(later, base.effective)
    schedules = (base, later, same_day)

    assert schedule_for(date(2026, 12, 31), schedules) == same_day
    assert schedule_for(date(2027, 1, 1), schedules) == later
    assert schedule_for(date(2025, 1, 1), (base, later)) == base


def test_new_schedule_reprices_from_its_effective_date() -> None:
    base = RE_SCHEDULES[0]
    new = raised(base, date(2026, 10, 10))
    first = datetime(2026, 10, 9, 12, tzinfo=DENVER).astimezone(UTC)
    readings = tuple(
        IntervalReading(first + timedelta(days=day), Decimal(1)) for day in (0, 1)
    )

    costs = [
        cost
        for _, cost in hourly_costs(
            readings, cycle_start_day=1, zone=DENVER, schedules=(base, new)
        )
    ]
    hours = 31 * 24

    assert costs[0] == base.tiers[0].non_summer + base.customer_charge / hours
    assert costs[1] == new.tiers[0].non_summer + new.customer_charge / hours


def test_current_rate_reports_tier_season_and_cycle() -> None:
    first = datetime(2026, 8, 19, tzinfo=DENVER).astimezone(UTC)
    readings = (
        IntervalReading(first - timedelta(hours=1), Decimal(500)),  # prior cycle
        IntervalReading(first, Decimal(400)),
        IntervalReading(first + timedelta(days=5), Decimal(400)),
    )

    info = current_rate(readings, date(2026, 9, 1), cycle_start_day=19, zone=DENVER)

    assert info.cycle_start == date(2026, 8, 19)
    assert info.cycle_end == date(2026, 9, 18)
    assert info.cycle_kwh == Decimal(800)
    assert info.summer
    assert info.tier == 2
    assert info.price == Decimal("0.1373")


def test_current_rate_at_exact_boundary_moves_to_next_tier() -> None:
    first = datetime(2026, 10, 19, tzinfo=DENVER).astimezone(UTC)
    readings = (IntervalReading(first, Decimal(750)),)

    info = current_rate(readings, date(2026, 10, 20), cycle_start_day=19, zone=DENVER)

    assert not info.summer
    assert info.tier == 2
    assert info.price == Decimal("0.1245")
