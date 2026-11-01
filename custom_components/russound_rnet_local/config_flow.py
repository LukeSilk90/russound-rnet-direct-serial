"""Config and options flows for Russound RNET Direct Serial.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from typing import Any

import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_BAUDRATE,
    CONF_CONTROLLERS,
    CONF_ENABLE_KEYPAD_CONTROLS,
    CONF_ENABLE_TONE_CONTROLS,
    CONF_SOURCE_NAMES,
    CONF_ZONE_NAMES,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTROLLERS,
    DEFAULT_ENABLE_KEYPAD_CONTROLS,
    DEFAULT_ENABLE_TONE_CONTROLS,
    DEFAULT_NAME,
    DOMAIN,
    SOURCE_COUNT,
    ZONES_PER_CONTROLLER,
)
from .rnet import RussoundSerial

BAUD_RATES = [9600, 19200, 38400, 57600, 115200]

DEFAULT_ZONE_NAMES = "Zone 1, Zone 2, Zone 3, Zone 4, Zone 5, Zone 6"
DEFAULT_SOURCE_NAMES = (
    "Source 1, Source 2, Source 3, Source 4, Source 5, Source 6"
)


def _detected_ports() -> list[str]:
    """Return serial devices, preferring stable by-id paths when present."""
    ports: list[str] = []
    for item in serial.tools.list_ports.comports():
        ports.append(item.device)
    return sorted(set(ports))


def _parse_names(value: str, required: int, prefix: str) -> list[str]:
    """Split a comma separated list and pad or trim it to the required length."""
    names = [part.strip() for part in value.split(",") if part.strip()]
    names.extend(f"{prefix} {index}" for index in range(len(names) + 1, required + 1))
    return names[:required]


class RussoundRnetLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Guide the user through connecting to an RNET controller."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect connection details and validate them against the hardware."""
        errors: dict[str, str] = {}
        ports = await self.hass.async_add_executor_job(_detected_ports)
        suggested_port = ports[0] if ports else "/dev/serial/by-id/"

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PORT])
            self._abort_if_unique_id_configured()

            client = RussoundSerial(user_input[CONF_PORT], user_input[CONF_BAUDRATE])

            def validate() -> bool:
                """Confirm controller 1 zone 1 answers a status request."""
                try:
                    if not client.connect():
                        return False
                    return client.get_zone_info(1, 1, retry=True) is not None
                finally:
                    client.close()

            if await self.hass.async_add_executor_job(validate):
                controllers = user_input[CONF_CONTROLLERS]
                data = dict(user_input)
                data[CONF_ZONE_NAMES] = _parse_names(
                    user_input[CONF_ZONE_NAMES],
                    controllers * ZONES_PER_CONTROLLER,
                    "Zone",
                )
                data[CONF_SOURCE_NAMES] = _parse_names(
                    user_input[CONF_SOURCE_NAMES], SOURCE_COUNT, "Source"
                )
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

            errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_PORT, default=suggested_port): str,
                vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(BAUD_RATES),
                vol.Required(CONF_CONTROLLERS, default=DEFAULT_CONTROLLERS): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=6)
                ),
                vol.Required(CONF_ZONE_NAMES, default=DEFAULT_ZONE_NAMES): str,
                vol.Required(CONF_SOURCE_NAMES, default=DEFAULT_SOURCE_NAMES): str,
                vol.Required(
                    CONF_ENABLE_TONE_CONTROLS, default=DEFAULT_ENABLE_TONE_CONTROLS
                ): bool,
                vol.Required(
                    CONF_ENABLE_KEYPAD_CONTROLS, default=DEFAULT_ENABLE_KEYPAD_CONTROLS
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"ports": ", ".join(ports) or "none detected"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return RussoundOptionsFlow()


class RussoundOptionsFlow(config_entries.OptionsFlow):
    """Allow names and optional entities to be changed after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Update zone names, source names and optional entity groups."""
        entry = self.config_entry
        settings = {**entry.data, **entry.options}

        if user_input is not None:
            controllers = user_input[CONF_CONTROLLERS]
            return self.async_create_entry(
                title="",
                data={
                    CONF_CONTROLLERS: controllers,
                    CONF_ZONE_NAMES: _parse_names(
                        user_input[CONF_ZONE_NAMES],
                        controllers * ZONES_PER_CONTROLLER,
                        "Zone",
                    ),
                    CONF_SOURCE_NAMES: _parse_names(
                        user_input[CONF_SOURCE_NAMES], SOURCE_COUNT, "Source"
                    ),
                    CONF_ENABLE_TONE_CONTROLS: user_input[CONF_ENABLE_TONE_CONTROLS],
                    CONF_ENABLE_KEYPAD_CONTROLS: user_input[CONF_ENABLE_KEYPAD_CONTROLS],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CONTROLLERS, default=settings[CONF_CONTROLLERS]
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=6)),
                vol.Required(
                    CONF_ZONE_NAMES, default=", ".join(settings[CONF_ZONE_NAMES])
                ): str,
                vol.Required(
                    CONF_SOURCE_NAMES, default=", ".join(settings[CONF_SOURCE_NAMES])
                ): str,
                vol.Required(
                    CONF_ENABLE_TONE_CONTROLS,
                    default=settings.get(
                        CONF_ENABLE_TONE_CONTROLS, DEFAULT_ENABLE_TONE_CONTROLS
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_KEYPAD_CONTROLS,
                    default=settings.get(
                        CONF_ENABLE_KEYPAD_CONTROLS, DEFAULT_ENABLE_KEYPAD_CONTROLS
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
