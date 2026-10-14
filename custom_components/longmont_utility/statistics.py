"""Aggregate source readings for Home Assistant long-term statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

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
from .models import IntervalReading, ParsedDay
from .tariff import RE_SCHEDULES, RateSchedule, hourly_costs


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

    readings = tuple(
        interval
        for day in sorted(days, key=lambda item: item.reading_date)
        for interval in day.intervals
    )
    return build_hourly_samples_from_readings(readings, baseline=baseline)


def build_hourly_samples_from_readings(
    readings: tuple[IntervalReading, ...],
    *,
    baseline: Decimal = Decimal(),
) -> list[HourlyStatistic]:
    """Build deterministic hourly statistics from retained source readings."""

    ordered = sorted(readings, key=lambda item: item.start.astimezone(UTC))
    samples: list[HourlyStatistic] = []
    cumulative = baseline
    for offset in range(0, len(ordered), 4):
        group = ordered[offset : offset + 4]
        if len(group) != 4:
            raise ValueError("source archive contains an incomplete hour")
        starts = [reading.start.astimezone(UTC) for reading in group]
        first = starts[0]
        if first.minute != 0 or any(
            start != first.replace(minute=15 * index)
            for index, start in enumerate(starts)
        ):
            raise ValueError("source intervals do not align to one hour")
        state = sum((reading.energy_kwh for reading in group), start=Decimal())
        cumulative += state
        samples.append(
            HourlyStatistic(
                start=first,
                state=float(state),
                sum=float(cumulative),
            )
        )
    return samples


def async_import_consumption_statistics(
    hass: HomeAssistant,
    statistic_id: str,
    readings: tuple[IntervalReading, ...],
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
    statistics = [
        StatisticData(start=item.start, state=item.state, sum=item.sum)
        for item in build_hourly_samples_from_readings(readings)
    ]
    async_add_external_statistics(hass, metadata, statistics)


def build_hourly_cost_samples(
    readings: tuple[IntervalReading, ...],
    *,
    cycle_start_day: int,
    zone: ZoneInfo,
    schedules: tuple[RateSchedule, ...] = RE_SCHEDULES,
) -> list[HourlyStatistic]:
    """Build cumulative hourly estimated-cost rows in US dollars."""

    samples: list[HourlyStatistic] = []
    cumulative = Decimal()
    for start, cost in hourly_costs(
        readings, cycle_start_day=cycle_start_day, zone=zone, schedules=schedules
    ):
        cumulative += cost
        samples.append(
            HourlyStatistic(start=start, state=float(cost), sum=float(cumulative))
        )
    return samples


def async_import_cost_statistics(
    hass: HomeAssistant,
    statistic_id: str,
    readings: tuple[IntervalReading, ...],
    *,
    cycle_start_day: int,
    zone: ZoneInfo,
    schedules: tuple[RateSchedule, ...] = RE_SCHEDULES,
) -> None:
    """Upsert estimated tiered cost for the complete retained archive."""

    validate_statistic_id(statistic_id)
    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name="Longmont electricity cost",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_class=None,
        unit_of_measurement="USD",
    )
    statistics = [
        StatisticData(start=item.start, state=item.state, sum=item.sum)
        for item in build_hourly_cost_samples(
            readings, cycle_start_day=cycle_start_day, zone=zone, schedules=schedules
        )
    ]
    async_add_external_statistics(hass, metadata, statistics)
