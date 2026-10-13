"""Config flow for Longmont Utility."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, override
from uuid import uuid4

import voluptuous as vol
from aiohttp import CookieJar
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client import InvalidAuth, LongmontPortalClient, MeterInfo, PortalError
from .const import (
    CONF_ACCOUNT_REF,
    CONF_BILLING_CYCLE_START_DAY,
    CONF_METER_REF,
    CONF_STATISTIC_SUFFIX,
    DEFAULT_BILLING_CYCLE_START_DAY,
    DOMAIN,
    PORTAL_BASE_URL,
)


def opaque_meter_unique_id(account_ref: str, meter_ref: str) -> str:
    """Derive a stable identifier without exposing portal references."""

    return sha256(f"{account_ref}\0{meter_ref}".encode()).hexdigest()[:32]


class LongmontUtilityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up and reauthenticate a Longmont electric meter."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the billing-cycle options flow."""

        return LongmontOptionsFlow()

    def __init__(self) -> None:
        self._credentials: dict[str, str] = {}
        self._meters: tuple[MeterInfo, ...] = ()

    async def _async_validate(self, username: str, password: str) -> None:
        session = async_create_clientsession(self.hass, cookie_jar=CookieJar())
        client = LongmontPortalClient(
            session,
            username,
            password,
            base_url=PORTAL_BASE_URL,
        )
        await client.authenticate()
        self._meters = await client.discover_meters()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            try:
                await self._async_validate(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except PortalError:
                errors["base"] = "cannot_connect"
            else:
                self._credentials = {
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                }
                return await self.async_step_meter()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select an authorized electric meter."""

        choices = {
            opaque_meter_unique_id(meter.account_ref, meter.meter_ref): meter.label
            for meter in self._meters
        }
        if user_input is not None:
            selected = str(user_input[CONF_METER_REF])
            meter = next(
                item
                for item in self._meters
                if opaque_meter_unique_id(item.account_ref, item.meter_ref) == selected
            )
            await self.async_set_unique_id(selected)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Longmont electricity",
                data={
                    **self._credentials,
                    CONF_ACCOUNT_REF: meter.account_ref,
                    CONF_METER_REF: meter.meter_ref,
                    CONF_STATISTIC_SUFFIX: uuid4().hex,
                },
            )
        return self.async_show_form(
            step_id="meter",
            data_schema=vol.Schema({vol.Required(CONF_METER_REF): vol.In(choices)}),
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate replacement credentials and reload the entry."""

        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            username = str(user_input[CONF_USERNAME]).strip()
            password = str(user_input[CONF_PASSWORD])
            try:
                await self._async_validate(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except PortalError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=entry.data[CONF_USERNAME],
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_BILLING_CYCLE_START_DAY,
            default=DEFAULT_BILLING_CYCLE_START_DAY,
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
    }
)


class LongmontOptionsFlow(OptionsFlow):
    """Configure the billing cycle used for tiered cost estimates."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the local day each billing cycle starts."""

        if user_input is not None:
            return self.async_create_entry(data=OPTIONS_SCHEMA(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
