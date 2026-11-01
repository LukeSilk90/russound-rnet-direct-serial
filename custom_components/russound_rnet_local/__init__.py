"""Russound RNET Direct Serial integration.

Controls Russound RNET controllers over a direct USB-to-RS232 connection,
without a TCP serial bridge.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONTROLLER,
    ATTR_ZONE,
    CONF_BAUDRATE,
    CONF_CONTROLLERS,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTROLLERS,
    DOMAIN,
    PLATFORMS,
    SERVICE_NORMALISE_ZONE,
    SERVICE_RESET_CONNECTION,
    ZONES_PER_CONTROLLER,
)
from .coordinator import RussoundCoordinator
from .rnet import RussoundSerial

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

NORMALISE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONTROLLER, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=6)
        ),
        vol.Required(ATTR_ZONE): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=ZONES_PER_CONTROLLER)
        ),
    }
)


@dataclass
class RussoundRuntimeData:
    """Runtime objects shared across platforms."""

    client: RussoundSerial
    coordinator: RussoundCoordinator


type RussoundConfigEntry = ConfigEntry[RussoundRuntimeData]


def _loaded_entries(hass: HomeAssistant) -> list[RussoundConfigEntry]:
    """Return config entries that currently hold runtime data."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-level actions."""

    async def async_reset_connection(call: ServiceCall) -> None:
        """Close, reopen and validate every Russound serial connection."""
        entries = _loaded_entries(hass)
        if not entries:
            raise HomeAssistantError("No loaded Russound RNET connection")

        results = await asyncio.gather(
            *[
                hass.async_add_executor_job(entry.runtime_data.client.manual_recover, 1, 1)
                for entry in entries
            ]
        )
        for entry in entries:
            await entry.runtime_data.coordinator.async_request_refresh()
        if not all(results):
            raise HomeAssistantError(
                "One or more Russound connections did not recover. Check the "
                "serial cable and confirm no other process is using the port."
            )

    async def async_normalise_zone(call: ServiceCall) -> None:
        """Reset inherited tone settings on a zone to neutral values."""
        entries = _loaded_entries(hass)
        if not entries:
            raise HomeAssistantError("No loaded Russound RNET connection")

        controller = call.data[ATTR_CONTROLLER]
        zone = call.data[ATTR_ZONE]
        for entry in entries:
            results = await hass.async_add_executor_job(
                entry.runtime_data.client.normalise_zone, controller, zone
            )
            failed = [name for name, ok in results.items() if not ok]
            if failed:
                _LOGGER.warning(
                    "Could not normalise %s on controller %s zone %s. Party mode "
                    "and do not disturb are unsupported on CAS44 and CAA66.",
                    ", ".join(failed),
                    controller,
                    zone,
                )
            await entry.runtime_data.coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_CONNECTION):
        hass.services.async_register(
            DOMAIN, SERVICE_RESET_CONNECTION, async_reset_connection
        )
    if not hass.services.has_service(DOMAIN, SERVICE_NORMALISE_ZONE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_NORMALISE_ZONE,
            async_normalise_zone,
            schema=NORMALISE_ZONE_SCHEMA,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RussoundConfigEntry) -> bool:
    """Open the serial connection and set up the platforms."""
    settings = {**entry.data, **entry.options}
    client = RussoundSerial(
        entry.data[CONF_PORT], entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
    )
    await hass.async_add_executor_job(client.connect)
    # Tolerate a controller that is still booting, for example after a power cut.
    await hass.async_add_executor_job(client.wait_until_ready, 1, 1)

    coordinator = RussoundCoordinator(
        hass, client, settings.get(CONF_CONTROLLERS, DEFAULT_CONTROLLERS)
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RussoundRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RussoundConfigEntry) -> bool:
    """Unload the platforms and close the serial port."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and getattr(entry, "runtime_data", None) is not None:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: RussoundConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
