"""Health sensors for Longmont Utility imports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATISTIC_SUFFIX
from .coordinator import LongmontConfigEntry, LongmontDataUpdateCoordinator

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="latest_interval",
        translation_key="latest_interval",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="data_age",
        translation_key="data_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
)

RATE_DESCRIPTION = SensorEntityDescription(
    key="electricity_rate",
    translation_key="electricity_rate",
    native_unit_of_measurement="USD/kWh",
    entity_category=EntityCategory.DIAGNOSTIC,
    suggested_display_precision=4,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LongmontConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up public-safe health sensors."""

    entities: list[SensorEntity] = [
        LongmontHealthSensor(entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(LongmontRateSensor(entry))
    async_add_entities(entities)


class LongmontHealthSensor(
    CoordinatorEntity[LongmontDataUpdateCoordinator], SensorEntity
):
    """Describe the health of the utility data import."""

    entity_description: SensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: LongmontConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(entry.runtime_data)
        self.entity_description = description
        suffix = entry.data[CONF_STATISTIC_SUFFIX]
        self._attr_unique_id = f"{suffix}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return a timestamp or derived age in hours."""

        data = self.coordinator.data
        if self.entity_description.key == "last_success":
            return data.last_success
        if self.entity_description.key == "latest_interval":
            return data.latest_interval
        if data.latest_interval is None:
            return None
        return (datetime.now(UTC) - data.latest_interval).total_seconds() / 3600


class LongmontRateSensor(
    CoordinatorEntity[LongmontDataUpdateCoordinator], SensorEntity
):
    """Marginal RE price at the current billing-cycle position."""

    entity_description = RATE_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(self, entry: LongmontConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        suffix = entry.data[CONF_STATISTIC_SUFFIX]
        self._attr_unique_id = f"{suffix}_{RATE_DESCRIPTION.key}"

    @property
    def native_value(self) -> float | None:
        """Return the price of the next kWh in this billing cycle."""

        info = self.coordinator.rate_info
        return None if info is None else float(info.price)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Describe the schedule, season, and cycle behind the price."""

        info = self.coordinator.rate_info
        if info is None:
            return None
        rates = self.coordinator.rates
        return {
            "tier": info.tier,
            "season": "summer" if info.summer else "non-summer",
            "customer_charge": float(info.schedule.customer_charge),
            "tiers": [
                {
                    "up_to_kwh": (
                        None if tier.limit_kwh is None else float(tier.limit_kwh)
                    ),
                    "non_summer": float(tier.non_summer),
                    "summer": float(tier.summer),
                }
                for tier in info.schedule.tiers
            ],
            "rates_effective": info.schedule.effective.isoformat(),
            "cycle_start": info.cycle_start.isoformat(),
            "cycle_end": info.cycle_end.isoformat(),
            "cycle_kwh_to_date": float(info.cycle_kwh),
            "rates_source": rates.source,
            "rates_last_checked": (
                rates.last_checked.isoformat() if rates.last_checked else None
            ),
        }
