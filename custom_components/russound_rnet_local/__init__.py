"""Russound RNET Direct Serial integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_BAUDRATE, DEFAULT_BAUDRATE, DOMAIN, PLATFORMS
from .rnet import RussoundSerial


@dataclass
class RussoundRuntimeData:
    """Runtime objects shared by platforms."""

    client: RussoundSerial


RussoundConfigEntry = ConfigEntry[RussoundRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register integration-level actions."""

    async def async_reset_connection(call: ServiceCall) -> None:
        """Reset every loaded Russound serial connection."""
        loaded = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.runtime_data is not None
        ]
        if not loaded:
            raise HomeAssistantError("No loaded Russound RNET connection")

        results = await asyncio.gather(
            *[
                hass.async_add_executor_job(entry.runtime_data.client.manual_recover, 1, 1)
                for entry in loaded
            ]
        )
        if not all(results):
            raise HomeAssistantError("One or more Russound connections did not recover")

        for entry in loaded:
            hass.bus.async_fire(f"{DOMAIN}_connection_reset", {"entry_id": entry.entry_id})

    import asyncio

    if not hass.services.has_service(DOMAIN, "reset_connection"):
        hass.services.async_register(DOMAIN, "reset_connection", async_reset_connection)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RussoundConfigEntry) -> bool:
    """Open the serial connection and set up entities."""
    client = RussoundSerial(
        entry.data[CONF_PORT],
        entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
    )
    await hass.async_add_executor_job(client.connect)
    await hass.async_add_executor_job(client.wait_until_ready, 1, 1)
    entry.runtime_data = RussoundRuntimeData(client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RussoundConfigEntry) -> bool:
    """Unload platforms and close the serial port."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data is not None:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: RussoundConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
