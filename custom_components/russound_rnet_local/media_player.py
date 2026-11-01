"""Media player entities for the Russound RNET Direct Serial integration.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_SOURCE_NAMES, CONF_ZONE_NAMES, ZONES_PER_CONTROLLER
from .entity import RussoundZoneEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one media player per configured zone."""
    runtime = entry.runtime_data
    settings = {**entry.data, **entry.options}
    zone_names = settings[CONF_ZONE_NAMES]
    sources = settings[CONF_SOURCE_NAMES]

    entities = []
    for index, zone_name in enumerate(zone_names, start=1):
        controller = ((index - 1) // ZONES_PER_CONTROLLER) + 1
        zone = ((index - 1) % ZONES_PER_CONTROLLER) + 1
        entities.append(
            RussoundZoneMediaPlayer(
                runtime.coordinator, entry.entry_id, controller, zone, zone_name, sources
            )
        )
    async_add_entities(entities)


class RussoundZoneMediaPlayer(RussoundZoneEntity, MediaPlayerEntity):
    """Power, source, volume and mute for a single Russound zone."""

    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator, entry_id, controller, zone, zone_name, sources):
        """Initialise the zone media player."""
        super().__init__(coordinator, entry_id, controller, zone, zone_name)
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}_media_player"
        self._attr_source_list = list(sources)
        self._muted = False

    @property
    def state(self) -> MediaPlayerState | None:
        """Return the zone power state."""
        data = self.zone_data
        if not data:
            return None
        return MediaPlayerState.ON if data.get("power") else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        """Return the zone volume as a fraction."""
        data = self.zone_data
        if "volume" not in data:
            return None
        return data["volume"] / 100.0

    @property
    def source(self) -> str | None:
        """Return the currently selected source name."""
        index = self.zone_data.get("source", 0) - 1
        if 0 <= index < len(self._attr_source_list):
            return self._attr_source_list[index]
        return None

    @property
    def is_volume_muted(self) -> bool:
        """Return the locally tracked mute state.

        RNET exposes mute only as a toggle and the All Zone Info reply does not
        report mute, so this cannot be read back from the controller.
        """
        return self._muted

    @property
    def extra_state_attributes(self) -> dict:
        """Add the read-only zone status fields to the standard attributes."""
        data = self.zone_data
        attributes = dict(super().extra_state_attributes)
        for key in ("system_on", "shared_source", "party_mode", "do_not_disturb"):
            if key in data:
                attributes[f"rnet_{key}"] = data[key]
        return attributes

    async def async_turn_on(self) -> None:
        """Turn the zone on."""
        await self._async_apply(self.client.set_power, self._controller, self._zone, 1)

    async def async_turn_off(self) -> None:
        """Turn the zone off."""
        await self._async_apply(self.client.set_power, self._controller, self._zone, 0)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the zone volume."""
        requested = round(max(0.0, min(1.0, volume)) * 100)
        await self._async_apply(
            self.client.set_volume, self._controller, self._zone, requested
        )

    async def async_volume_up(self) -> None:
        """Step the volume up by one RNET increment."""
        current = self.volume_level or 0.0
        await self.async_set_volume_level(min(1.0, current + 0.02))

    async def async_volume_down(self) -> None:
        """Step the volume down by one RNET increment."""
        current = self.volume_level or 0.0
        await self.async_set_volume_level(max(0.0, current - 0.02))

    async def async_mute_volume(self, mute: bool) -> None:
        """Toggle mute, tracking the assumed state locally."""
        if mute == self._muted:
            return
        healthy = await self.hass.async_add_executor_job(
            self.client.toggle_mute, self._controller, self._zone
        )
        if healthy:
            self._muted = mute
            self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        """Select an input source."""
        if source not in self._attr_source_list:
            _LOGGER.warning("Unknown Russound source %r", source)
            return
        await self._async_apply(
            self.client.set_source,
            self._controller,
            self._zone,
            self._attr_source_list.index(source),
        )
