"""Polling coordinator for the Russound RNET Direct Serial integration.

A single All Zone Info request returns power, source, volume, bass, treble,
loudness, balance, system-on, shared-source, party mode and do-not-disturb.
Polling that one frame per zone therefore feeds every entity, which matters
because RNET requires roughly 100 ms between messages.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, ZONES_PER_CONTROLLER
from .rnet import RussoundSerial

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)


class RussoundCoordinator(DataUpdateCoordinator[dict[tuple[int, int], dict]]):
    """Poll every configured zone with one RNET request each."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RussoundSerial,
        controllers: int,
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )
        self.client = client
        self.controllers = controllers
        self._zones = [
            (controller, zone)
            for controller in range(1, controllers + 1)
            for zone in range(1, ZONES_PER_CONTROLLER + 1)
        ]

    def _poll(self) -> dict[tuple[int, int], dict]:
        """Read all zones. Runs in the executor because the client blocks."""
        results: dict[tuple[int, int], dict] = {}
        for controller, zone in self._zones:
            try:
                status = self.client.get_zone_info(controller, zone, retry=True)
            except Exception as err:  # noqa: BLE001 - never let one zone kill the poll
                _LOGGER.warning(
                    "Error polling controller %s zone %s: %s", controller, zone, err
                )
                status = None
            results[(controller, zone)] = status or {}
        return results

    async def _async_update_data(self) -> dict[tuple[int, int], dict]:
        """Fetch the latest state for every zone."""
        return await self.hass.async_add_executor_job(self._poll)

    def zone_data(self, controller: int, zone: int) -> dict:
        """Return the most recent data for one zone."""
        if not self.data:
            return {}
        return self.data.get((controller, zone), {})

    def zone_available(self, controller: int, zone: int) -> bool:
        """Return True when the last poll produced a usable reply."""
        return bool(self.zone_data(controller, zone))
