"""Shared base entity for the Russound RNET Direct Serial integration.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_CONTROLLER, ATTR_ZONE, DOMAIN
from .coordinator import RussoundCoordinator


class RussoundZoneEntity(CoordinatorEntity[RussoundCoordinator]):
    """Base class binding an entity to one controller/zone pair."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RussoundCoordinator,
        entry_id: str,
        controller: int,
        zone: int,
        zone_name: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._controller = controller
        self._zone = zone
        self._zone_name = zone_name
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{controller}_{zone}")},
            name=zone_name,
            manufacturer="Russound",
            model=f"RNET zone (controller {controller}, zone {zone})",
            via_device=(DOMAIN, entry_id),
        )

    @property
    def client(self):
        """Return the shared serial client."""
        return self.coordinator.client

    @property
    def zone_data(self) -> dict:
        """Return the latest polled data for this zone."""
        return self.coordinator.zone_data(self._controller, self._zone)

    @property
    def available(self) -> bool:
        """Return True only when the zone last answered an RNET request."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.zone_available(self._controller, self._zone)
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the controller/zone identity and serial health."""
        return {
            ATTR_CONTROLLER: self._controller,
            ATTR_ZONE: self._zone,
            **self.client.diagnostics,
        }

    async def _async_apply(self, func, *args) -> None:
        """Run a blocking client call then refresh coordinator state."""
        await self.hass.async_add_executor_job(func, *args)
        await self.coordinator.async_request_refresh()
