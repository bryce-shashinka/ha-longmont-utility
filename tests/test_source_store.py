from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from custom_components.longmont_utility.csv_parser import parse_smart_meter_csv
from custom_components.longmont_utility.source_store import SourceArchive

DENVER = ZoneInfo("America/Denver")


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = data


def parsed_day(csv_payload_factory, value: str = "0.125"):
    intervals = [Decimal(value)] * 96
    total = sum(intervals, Decimal())
    payload = csv_payload_factory([(date(2026, 8, 5), intervals, total)])
    return parse_smart_meter_csv(payload, DENVER)[0]


def test_archive_preserves_exact_values_at_utc_timestamps(
    csv_payload_factory,
) -> None:
    store = MemoryStore()
    archive = SourceArchive(store)

    asyncio.run(archive.async_upsert((parsed_day(csv_payload_factory),)))

    assert store.data is not None
    assert len(store.data["readings"]) == 96
    assert store.data["readings"]["2026-08-05T06:00:00+00:00"] == "0.125"
    restored = asyncio.run(archive.async_read())
    assert restored[0].energy_kwh == Decimal("0.125")
    assert restored[0].start.isoformat() == "2026-08-05T06:00:00+00:00"


def test_archive_upsert_replaces_revisions_without_duplicates(
    csv_payload_factory,
) -> None:
    store = MemoryStore()
    archive = SourceArchive(store)
    original = parsed_day(csv_payload_factory, "0.125")
    revised = parsed_day(csv_payload_factory, "0.250")

    asyncio.run(archive.async_upsert((original,)))
    asyncio.run(archive.async_upsert((revised,)))

    restored = asyncio.run(archive.async_read())
    assert len(restored) == 96
    assert {reading.energy_kwh for reading in restored} == {Decimal("0.250")}


def test_archive_reads_legacy_empty_state() -> None:
    archive = SourceArchive(MemoryStore())

    assert asyncio.run(archive.async_read()) == ()

