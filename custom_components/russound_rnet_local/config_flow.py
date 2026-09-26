"""Config flow for Russound RNET Direct Serial."""

from __future__ import annotations

import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_BAUDRATE,
    CONF_CONTROLLERS,
    CONF_SOURCE_NAMES,
    CONF_ZONE_NAMES,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTROLLERS,
    DEFAULT_NAME,
    DOMAIN,
    ZONES_PER_CONTROLLER,
)
from .rnet import RussoundSerial


def _serial_ports() -> list[str]:
    """Return stable serial paths where available."""
    ports = []
    for item in serial.tools.list_ports.comports():
        ports.append(item.device)
    return sorted(set(ports))


def _parse_names(value: str, required: int, prefix: str) -> list[str]:
    names = [part.strip() for part in value.split(",") if part.strip()]
    names.extend(f"{prefix} {index}" for index in range(len(names) + 1, required + 1))
    return names[:required]


class RussoundRnetLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle UI setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Configure and validate a direct serial connection."""
        errors = {}
        ports = await self.hass.async_add_executor_job(_serial_ports)
        default_port = ports[0] if ports else "/dev/serial/by-id/"

        if user_input is not None:
            client = RussoundSerial(user_input[CONF_PORT], user_input[CONF_BAUDRATE])

            def validate() -> bool:
                try:
                    if not client.connect():
                        return False
                    return client.get_zone_info(1, 1, retry=False) is not None
                finally:
                    client.close()

            if await self.hass.async_add_executor_job(validate):
                await self.async_set_unique_id(user_input[CONF_PORT])
                self._abort_if_unique_id_configured()
                controllers = user_input[CONF_CONTROLLERS]
                data = dict(user_input)
                data[CONF_ZONE_NAMES] = _parse_names(
                    user_input[CONF_ZONE_NAMES], controllers * ZONES_PER_CONTROLLER, "Zone"
                )
                data[CONF_SOURCE_NAMES] = _parse_names(
                    user_input[CONF_SOURCE_NAMES], 6, "Source"
                )
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)
            errors["base"] = "cannot_connect"

        port_schema = str
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_PORT, default=default_port): port_schema,
                vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(
                    [9600, 19200, 38400, 57600, 115200]
                ),
                vol.Required(CONF_CONTROLLERS, default=DEFAULT_CONTROLLERS): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=6)
                ),
                vol.Required(
                    CONF_ZONE_NAMES,
                    default="Kitchen, Office, Master Bedroom, En-suite, Bathroom, Bedroom 2",
                ): str,
                vol.Required(
                    CONF_SOURCE_NAMES,
                    default="Source 1, Source 2, Source 3, Source 4, Source 5, Source 6",
                ): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return RussoundOptionsFlow()


class RussoundOptionsFlow(config_entries.OptionsFlow):
    """Allow renaming zones and sources without re-adding the integration."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        if user_input is not None:
            controllers = user_input[CONF_CONTROLLERS]
            return self.async_create_entry(
                title="",
                data={
                    CONF_CONTROLLERS: controllers,
                    CONF_ZONE_NAMES: _parse_names(
                        user_input[CONF_ZONE_NAMES], controllers * ZONES_PER_CONTROLLER, "Zone"
                    ),
                    CONF_SOURCE_NAMES: _parse_names(user_input[CONF_SOURCE_NAMES], 6, "Source"),
                },
            )
        current_controllers = entry.options.get(CONF_CONTROLLERS, entry.data[CONF_CONTROLLERS])
        current_zones = entry.options.get(CONF_ZONE_NAMES, entry.data[CONF_ZONE_NAMES])
        current_sources = entry.options.get(CONF_SOURCE_NAMES, entry.data[CONF_SOURCE_NAMES])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONTROLLERS, default=current_controllers): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=6)
                    ),
                    vol.Required(CONF_ZONE_NAMES, default=", ".join(current_zones)): str,
                    vol.Required(CONF_SOURCE_NAMES, default=", ".join(current_sources)): str,
                }
            ),
        )
