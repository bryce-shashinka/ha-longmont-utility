"""Longmont Utility integration."""

from aiohttp import CookieJar
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client import LongmontPortalClient
from .const import PORTAL_BASE_URL
from .coordinator import LongmontConfigEntry, LongmontDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: LongmontConfigEntry
) -> bool:
    """Set up a Longmont Utility config entry."""

    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    client = LongmontPortalClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        base_url=PORTAL_BASE_URL,
    )
    coordinator = LongmontDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: LongmontConfigEntry
) -> bool:
    """Unload a Longmont Utility config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
