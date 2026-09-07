from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from custom_components.longmont_utility.csv_parser import parse_smart_meter_csv
from custom_components.longmont_utility.statistics import (
    async_import_consumption_statistics,
    build_hourly_statistic_samples,
    validate_statistic_id,
)

DENVER = ZoneInfo("America/Denver")


def test_four_source_intervals_become_one_hourly_statistic(
    csv_payload_factory,
) -> None:
    intervals = [Decimal("0.100"), Decimal("0.200"), Decimal("0.300"), Decimal("0.400")]
    intervals += [Decimal("0.125")] * 92
    payload = csv_payload_factory(
        [(date(2026, 8, 5), intervals, sum(intervals, Decimal()))]
    )
    day = parse_smart_meter_csv(payload, DENVER)[0]

    samples = build_hourly_statistic_samples((day,), baseline=Decimal("5.000"))

    assert len(samples) == 24
    assert samples[0].start.isoformat() == "2026-08-05T06:00:00+00:00"
    assert samples[0].state == 1.0
    assert samples[0].sum == 6.0
    assert samples[1].state == 0.5
    assert samples[1].sum == 6.5
    assert samples[-1].sum == 17.5


def test_hourly_samples_are_sorted_across_unsorted_days(csv_payload_factory) -> None:
    intervals = [Decimal("0.125")] * 96
    payload = csv_payload_factory(
        [
            (date(2026, 8, 6), intervals, Decimal("12.000")),
            (date(2026, 8, 5), intervals, Decimal("12.000")),
        ]
    )
    days = parse_smart_meter_csv(payload, DENVER)

    samples = build_hourly_statistic_samples(tuple(reversed(days)))

    assert len(samples) == 48
    assert samples[0].start < samples[-1].start
    assert samples[-1].sum == 24.0


@pytest.mark.parametrize(
    "statistic_id",
    ["sensor.longmont_energy", "other:energy", "longmont_utility:"],
)
def test_rejects_statistic_ids_outside_integration_namespace(
    statistic_id: str,
) -> None:
    with pytest.raises(ValueError, match="statistic ID"):
        validate_statistic_id(statistic_id)


def test_accepts_opaque_integration_statistic_id() -> None:
    validate_statistic_id("longmont_utility:0123456789abcdef_energy_consumption")


def test_imports_hourly_samples_with_energy_metadata(
    csv_payload_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intervals = [Decimal("0.125")] * 96
    payload = csv_payload_factory(
        [(date(2026, 8, 5), intervals, Decimal("12.000"))]
    )
    day = parse_smart_meter_csv(payload, DENVER)[0]
    captured: dict[str, object] = {}

    def capture_import(hass, metadata, statistics) -> None:
        captured["hass"] = hass
        captured["metadata"] = metadata
        captured["statistics"] = list(statistics)

    monkeypatch.setattr(
        "custom_components.longmont_utility.statistics.async_add_external_statistics",
        capture_import,
    )
    hass = object()

    async_import_consumption_statistics(
        hass,
        "longmont_utility:0123456789abcdef_energy_consumption",
        (day,),
    )

    metadata = captured["metadata"]
    statistics = captured["statistics"]
    assert captured["hass"] is hass
    assert metadata["source"] == "longmont_utility"
    assert metadata["unit_of_measurement"] == "kWh"
    assert metadata["has_sum"] is True
    assert len(statistics) == 24
    assert statistics[0]["state"] == 0.5
    assert statistics[0]["sum"] == 0.5
