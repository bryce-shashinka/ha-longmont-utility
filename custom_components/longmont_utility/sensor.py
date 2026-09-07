"""Health sensors for Longmont Utility imports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LongmontConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up public-safe health sensors."""

    async_add_entities(
        LongmontHealthSensor(entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


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
