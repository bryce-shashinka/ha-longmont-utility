"""Longmont Utility integration."""

from aiohttp import CookieJar
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .client import LongmontPortalClient, async_portal_ssl_context
from .const import DOMAIN, PORTAL_BASE_URL, SOURCE_STORE_VERSION
from .coordinator import LongmontConfigEntry, LongmontDataUpdateCoordinator
from .rates import RATES_STORE_VERSION

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: LongmontConfigEntry) -> bool:
    """Set up a Longmont Utility config entry."""

    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    client = LongmontPortalClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        base_url=PORTAL_BASE_URL,
        ssl_context=await async_portal_ssl_context(hass),
    )
    coordinator = LongmontDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: LongmontConfigEntry
) -> None:
    """Reload so a changed billing cycle recalculates estimated cost."""

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LongmontConfigEntry) -> bool:
    """Unload a Longmont Utility config entry."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: LongmontConfigEntry) -> None:
    """Remove the retained archives when their config entry is deleted."""

    for version, kind in (
        (SOURCE_STORE_VERSION, "source"),
        (RATES_STORE_VERSION, "rates"),
    ):
        store = Store[dict[str, object]](
            hass,
            version,
            f"{DOMAIN}.{entry.entry_id}.{kind}",
            private=True,
        )
        await store.async_remove()
