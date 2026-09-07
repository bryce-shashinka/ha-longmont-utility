"""Refresh orchestration for Longmont utility consumption."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import override
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    InvalidAuth,
    LongmontPortalClient,
    MeterInfo,
    PortalError,
)
from .const import (
    CONF_ACCOUNT_REF,
    CONF_METER_REF,
    CONF_STATISTIC_SUFFIX,
    DOMAIN,
    INITIAL_IMPORT_DAYS,
    PORTAL_TIME_ZONE,
    REFRESH_DAYS,
    SOURCE_STORE_VERSION,
)
from .source_store import SourceArchive
from .statistics import async_import_consumption_statistics

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoordinatorData:
    """Public-safe refresh state exposed to entities and diagnostics."""

    last_success: datetime
    latest_interval: datetime | None
    last_error_category: str | None = None


type LongmontConfigEntry = ConfigEntry["LongmontDataUpdateCoordinator"]


def refresh_window(today: date, *, initial: bool) -> tuple[date, date]:
    """Return an inclusive range ending on the last complete local date."""

    end = today - timedelta(days=1)
    days = INITIAL_IMPORT_DAYS if initial else REFRESH_DAYS
    return end - timedelta(days=days - 1), end


class LongmontDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Download, retain, aggregate, and publish Longmont usage."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LongmontConfigEntry,
        client: LongmontPortalClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(days=1),
        )
        self._entry = entry
        self._client = client
        self._initial = True
        store = Store[dict[str, object]](
            hass,
            SOURCE_STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.source",
            private=True,
            atomic_writes=True,
        )
        self.archive = SourceArchive(store)

    @property
    def statistic_id(self) -> str:
        """Return the non-identifying external statistic ID."""

        return (
            f"{DOMAIN}:{self._entry.data[CONF_STATISTIC_SUFFIX]}"
            "_energy_consumption"
        )

    @override
    async def _async_update_data(self) -> CoordinatorData:
        try:
            await self._client.authenticate()
            meter = MeterInfo(
                account_ref=self._entry.data[CONF_ACCOUNT_REF],
                meter_ref=self._entry.data[CONF_METER_REF],
                label="Longmont electric meter",
            )
            local_today = datetime.now(ZoneInfo(PORTAL_TIME_ZONE)).date()
            start, end = refresh_window(local_today, initial=self._initial)
            days = await self._client.download_usage(meter, start, end)
            await self.archive.async_upsert(days)
            readings = await self.archive.async_read()
            async_import_consumption_statistics(
                self.hass, self.statistic_id, readings
            )
        except InvalidAuth as err:
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed("utility portal authentication failed") from err
        except PortalError as err:
            raise UpdateFailed("utility portal refresh failed") from err

        self._initial = False
        latest = readings[-1].start if readings else None
        return CoordinatorData(datetime.now(UTC), latest)
