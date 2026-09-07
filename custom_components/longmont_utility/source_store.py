"""Full-fidelity local archive for normalized source readings."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from .models import IntervalReading, ParsedDay


class StorageBackend(Protocol):
    """Subset of Home Assistant Store used by the source archive."""

    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


class SourceArchive:
    """Upsert exact source intervals by their UTC timestamp."""

    def __init__(self, store: StorageBackend) -> None:
        self._store = store

    async def async_upsert(self, days: tuple[ParsedDay, ...]) -> None:
        """Atomically merge validated days into the retained source archive."""

        data = await self._store.async_load() or {"readings": {}}
        readings: dict[str, str] = dict(data.get("readings", {}))
        for day in days:
            for interval in day.intervals:
                timestamp = interval.start.astimezone(UTC).isoformat()
                readings[timestamp] = str(interval.energy_kwh)
        await self._store.async_save({"readings": dict(sorted(readings.items()))})

    async def async_read(self) -> tuple[IntervalReading, ...]:
        """Return all retained readings ordered by UTC timestamp."""

        data = await self._store.async_load() or {"readings": {}}
        readings = data.get("readings", {})
        return tuple(
            IntervalReading(
                start=datetime.fromisoformat(timestamp),
                energy_kwh=Decimal(value),
            )
            for timestamp, value in sorted(readings.items())
        )
