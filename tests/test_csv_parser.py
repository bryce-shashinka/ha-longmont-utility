from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from zoneinfo import ZoneInfo

import pytest

from custom_components.longmont_utility.csv_parser import (
    CsvValidationError,
    parse_smart_meter_csv,
)

DENVER = ZoneInfo("America/Denver")


def ordinary_intervals() -> list[Decimal]:
    return [Decimal("0.125") for _ in range(96)]


def test_parses_misleading_header_into_quarter_hour_intervals(
    csv_payload_factory,
) -> None:
    payload = csv_payload_factory(
        [(date(2026, 8, 5), ordinary_intervals(), Decimal("12.000"))],
        line_ending="\r\n",
    )

    parsed = parse_smart_meter_csv(payload, DENVER)

    assert len(parsed) == 1
    assert parsed[0].reading_date == date(2026, 8, 5)
    assert len(parsed[0].intervals) == 96
    assert parsed[0].intervals[0].start == datetime(2026, 8, 5, 0, 0, tzinfo=DENVER)
    assert parsed[0].intervals[1].start == datetime(2026, 8, 5, 0, 15, tzinfo=DENVER)
    assert parsed[0].intervals[-1].start == datetime(2026, 8, 5, 23, 45, tzinfo=DENVER)
    assert parsed[0].intervals[0].energy_kwh == Decimal("0.125")
    assert parsed[0].total_kwh == Decimal("12.000")


@pytest.mark.parametrize(
    ("intervals", "total", "message"),
    [
        ([Decimal("0.125")] * 95, Decimal("11.875"), "96 interval"),
        (
            [Decimal("0.125")] * 95 + [Decimal("-0.1")],
            Decimal("11.775"),
            "non-negative",
        ),
        ([Decimal("0.125")] * 95 + [Decimal("NaN")], Decimal("11.875"), "finite"),
        ([Decimal("0.125")] * 96, Decimal("12.010"), "daily total"),
    ],
)
def test_rejects_invalid_interval_rows(
    csv_payload_factory,
    intervals: list[Decimal],
    total: Decimal,
    message: str,
) -> None:
    payload = csv_payload_factory([(date(2026, 8, 5), intervals, total)])

    with pytest.raises(CsvValidationError, match=message):
        parse_smart_meter_csv(payload, DENVER)


def test_rejects_duplicate_dates(csv_payload_factory) -> None:
    row = (date(2026, 8, 5), ordinary_intervals(), Decimal("12.000"))
    payload = csv_payload_factory([row, row])

    with pytest.raises(CsvValidationError, match="duplicate"):
        parse_smart_meter_csv(payload, DENVER)


@pytest.mark.parametrize("transition_date", [date(2026, 3, 8), date(2026, 11, 1)])
def test_rejects_96_values_on_daylight_saving_transition(
    csv_payload_factory,
    transition_date: date,
) -> None:
    payload = csv_payload_factory(
        [(transition_date, ordinary_intervals(), Decimal("12.000"))]
    )

    with pytest.raises(CsvValidationError, match="daylight-saving"):
        parse_smart_meter_csv(payload, DENVER)


def test_sorts_rows_and_rejects_empty_payload(csv_payload_factory) -> None:
    payload = csv_payload_factory(
        [
            (date(2026, 8, 6), ordinary_intervals(), Decimal("12.000")),
            (date(2026, 8, 5), ordinary_intervals(), Decimal("12.000")),
        ]
    )
    assert [day.reading_date for day in parse_smart_meter_csv(payload, DENVER)] == [
        date(2026, 8, 5),
        date(2026, 8, 6),
    ]

    with pytest.raises(CsvValidationError, match="empty"):
        parse_smart_meter_csv("", DENVER)


def test_intervals_are_exactly_fifteen_minutes_apart(csv_payload_factory) -> None:
    payload = csv_payload_factory(
        [(date(2026, 1, 15), ordinary_intervals(), Decimal("12.000"))]
    )
    intervals = parse_smart_meter_csv(payload, DENVER)[0].intervals

    assert all(
        right.start - left.start == timedelta(minutes=15)
        for left, right in pairwise(intervals)
    )
