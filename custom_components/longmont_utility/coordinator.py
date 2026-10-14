"""Refresh orchestration for Longmont utility consumption."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import override
from zoneinfo import ZoneInfo

from aiohttp import ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    CONF_BILLING_CYCLE_START_DAY,
    CONF_METER_REF,
    CONF_STATISTIC_SUFFIX,
    DEFAULT_BILLING_CYCLE_START_DAY,
    DOMAIN,
    INITIAL_IMPORT_DAYS,
    PORTAL_TIME_ZONE,
    REFRESH_DAYS,
    SOURCE_STORE_VERSION,
)
from .models import IntervalReading
from .rates import (
    FAILURES_BEFORE_REPAIR,
    RATES_STORE_VERSION,
    RATES_URL,
    RateTracker,
)
from .source_store import SourceArchive
from .statistics import (
    async_import_consumption_statistics,
    async_import_cost_statistics,
)
from .tariff import CurrentRate, current_rate

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
        rates_store = Store[dict[str, object]](
            hass,
            RATES_STORE_VERSION,
            f"{DOMAIN}.{entry.entry_id}.rates",
            private=True,
            atomic_writes=True,
        )
        self.rates = RateTracker(rates_store, self._async_fetch_rates_page)
        self.rate_info: CurrentRate | None = None

    async def _async_fetch_rates_page(self) -> str:
        session = async_get_clientsession(self.hass)
        async with session.get(RATES_URL, timeout=ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.text()

    @property
    def _zone(self) -> ZoneInfo:
        return ZoneInfo(PORTAL_TIME_ZONE)

    @property
    def _cycle_start_day(self) -> int:
        return int(
            self._entry.options.get(
                CONF_BILLING_CYCLE_START_DAY, DEFAULT_BILLING_CYCLE_START_DAY
            )
        )

    async def _async_check_rates(self) -> bool:
        """Run the daily rate check; return True when prices changed."""

        now = datetime.now(UTC)
        try:
            result = await self.rates.async_check(
                now.astimezone(self._zone).date(), now
            )
        except Exception:
            _LOGGER.exception("Unexpected error checking Longmont rates")
            return False
        entry_id = self._entry.entry_id
        unreadable = f"rates_unreadable_{entry_id}"
        if result.attempted and result.error is None:
            ir.async_delete_issue(self.hass, DOMAIN, unreadable)
        elif self.rates.consecutive_failures >= FAILURES_BEFORE_REPAIR:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                unreadable,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="rates_unreadable",
                translation_placeholders={
                    "days": str(self.rates.consecutive_failures),
                    "url": RATES_URL,
                },
            )
        if result.changed is None:
            return False
        effective = result.changed.effective.isoformat()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"rates_changed_{entry_id}_{effective}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="rates_changed",
            translation_placeholders={"effective": effective, "url": RATES_URL},
        )
        return True

    def _import_cost(self, readings: tuple[IntervalReading, ...]) -> None:
        async_import_cost_statistics(
            self.hass,
            self.cost_statistic_id,
            readings,
            cycle_start_day=self._cycle_start_day,
            zone=self._zone,
            schedules=self.rates.schedules,
        )
        self.rate_info = current_rate(
            readings,
            datetime.now(self._zone).date(),
            cycle_start_day=self._cycle_start_day,
            zone=self._zone,
            schedules=self.rates.schedules,
        )

    async def _async_reprice_retained(self) -> None:
        """Recalculate cost from the archive after a rate change."""

        self._import_cost(await self.archive.async_read())

    @property
    def statistic_id(self) -> str:
        """Return the non-identifying external statistic ID."""

        return f"{DOMAIN}:{self._entry.data[CONF_STATISTIC_SUFFIX]}_energy_consumption"

    @property
    def cost_statistic_id(self) -> str:
        """Return the non-identifying external estimated-cost statistic ID."""

        return f"{DOMAIN}:{self._entry.data[CONF_STATISTIC_SUFFIX]}_energy_cost"

    @override
    async def _async_update_data(self) -> CoordinatorData:
        rates_changed = await self._async_check_rates()
        try:
            await self._client.authenticate()
            meter = MeterInfo(
                account_ref=self._entry.data[CONF_ACCOUNT_REF],
                meter_ref=self._entry.data[CONF_METER_REF],
                label="Longmont electric meter",
            )
            local_today = datetime.now(self._zone).date()
            start, end = refresh_window(local_today, initial=self._initial)
            days = await self._client.download_usage(meter, start, end)
            await self.archive.async_upsert(days)
            readings = await self.archive.async_read()
            async_import_consumption_statistics(self.hass, self.statistic_id, readings)
            self._import_cost(readings)
        except InvalidAuth as err:
            if rates_changed:
                await self._async_reprice_retained()
            self._entry.async_start_reauth(self.hass)
            raise UpdateFailed("utility portal authentication failed") from err
        except PortalError as err:
            if rates_changed:
                await self._async_reprice_retained()
            raise UpdateFailed("utility portal refresh failed") from err

        self._initial = False
        latest = readings[-1].start if readings else None
        return CoordinatorData(datetime.now(UTC), latest)
