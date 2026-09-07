"""Aggregate source readings for Home Assistant long-term statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.util.unit_conversion import EnergyConverter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .models import ParsedDay


@dataclass(frozen=True, slots=True)
class HourlyStatistic:
    """Framework-independent representation of one hourly statistic row."""

    start: datetime
    state: float
    sum: float


def validate_statistic_id(statistic_id: str) -> None:
    """Require an opaque statistic ID owned by this integration."""

    prefix = f"{DOMAIN}:"
    if not statistic_id.startswith(prefix) or statistic_id == prefix:
        raise ValueError("statistic ID must belong to the Longmont integration")


def build_hourly_statistic_samples(
    days: tuple[ParsedDay, ...],
    *,
    baseline: Decimal = Decimal(),
) -> list[HourlyStatistic]:
    """Sum four quarter-hour readings into each cumulative hourly row."""

    cumulative = baseline
    samples: list[HourlyStatistic] = []
    for day in sorted(days, key=lambda item: item.reading_date):
        intervals = day.intervals
        if len(intervals) != 96:
            raise ValueError("a source day must contain 96 intervals")
        for offset in range(0, 96, 4):
            group = intervals[offset : offset + 4]
            first = group[0].start
            if first.minute != 0 or any(
                reading.start.hour != first.hour
                or reading.start.date() != first.date()
                for reading in group
            ):
                raise ValueError("source intervals do not align to one local hour")
            state = sum(
                (reading.energy_kwh for reading in group),
                start=Decimal(),
            )
            cumulative += state
            samples.append(
                HourlyStatistic(
                    start=first.astimezone(UTC),
                    state=float(state),
                    sum=float(cumulative),
                )
            )
    return samples


def async_import_consumption_statistics(
    hass: HomeAssistant,
    statistic_id: str,
    days: tuple[ParsedDay, ...],
) -> None:
    """Upsert the complete retained archive into HA's hourly statistics."""

    validate_statistic_id(statistic_id)
    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name="Longmont electricity consumption",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_class=EnergyConverter.UNIT_CLASS,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    statistics = (
        StatisticData(start=item.start, state=item.state, sum=item.sum)
        for item in build_hourly_statistic_samples(days)
    )
    async_add_external_statistics(hass, metadata, statistics)
