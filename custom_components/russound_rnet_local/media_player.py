"""Media player entities for Russound RNET Direct Serial."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CONTROLLERS,
    CONF_SOURCE_NAMES,
    CONF_ZONE_NAMES,
    DOMAIN,
    ZONES_PER_CONTROLLER,
)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one media player per configured zone."""
    settings = {**entry.data, **entry.options}
    client = entry.runtime_data.client
    zone_names = settings[CONF_ZONE_NAMES]
    source_names = settings[CONF_SOURCE_NAMES]
    controllers = settings[CONF_CONTROLLERS]

    entities = [
        RussoundRNetZone(
            client=client,
            entry_id=entry.entry_id,
            controller=((index - 1) // ZONES_PER_CONTROLLER) + 1,
            zone=((index - 1) % ZONES_PER_CONTROLLER) + 1,
            name=zone_names[index - 1],
            sources=source_names,
        )
        for index in range(1, controllers * ZONES_PER_CONTROLLER + 1)
    ]
    async_add_entities(entities, True)

    async def refresh_after_reset(event: Event) -> None:
        if event.data.get("entry_id") != entry.entry_id:
            return
        for entity in entities:
            entity.async_schedule_update_ha_state(force_refresh=True)

    entry.async_on_unload(hass.bus.async_listen(f"{DOMAIN}_connection_reset", refresh_after_reset))


class RussoundRNetZone(MediaPlayerEntity):
    """Representation of one Russound zone."""

    _attr_should_poll = True
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, client, entry_id, controller, zone, name, sources):
        self._client = client
        self._controller = controller
        self._zone = zone
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}"
        self._attr_source_list = list(sources)
        self._attr_state = MediaPlayerState.OFF
        self._attr_volume_level = 0.0
        self._attr_is_volume_muted = False
        self._attr_available = False
        self._attr_source = None

    @property
    def extra_state_attributes(self):
        return {"controller": self._controller, "zone": self._zone, **self._client.diagnostics}

    def _apply_status(self, status: dict) -> None:
        self._attr_available = True
        self._attr_state = MediaPlayerState.ON if status["power"] else MediaPlayerState.OFF
        self._attr_volume_level = status["volume"] / 100.0
        index = status["source"] - 1
        if 0 <= index < len(self._attr_source_list):
            self._attr_source = self._attr_source_list[index]

    def update(self) -> None:
        try:
            status = self._client.get_zone_info(self._controller, self._zone, retry=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Error polling controller %s zone %s: %s", self._controller, self._zone, err)
            self._attr_available = False
            return
        if status is None:
            self._attr_available = False
            return
        self._apply_status(status)

    def turn_on(self) -> None:
        self._apply_result(self._client.set_power(self._controller, self._zone, 1), "turn on")

    def turn_off(self) -> None:
        self._apply_result(self._client.set_power(self._controller, self._zone, 0), "turn off")

    def set_volume_level(self, volume: float) -> None:
        requested = round(max(0.0, min(1.0, volume)) * 100)
        self._apply_result(
            self._client.set_volume(self._controller, self._zone, requested), "set volume"
        )

    def volume_up(self) -> None:
        self.set_volume_level(min(1.0, self._attr_volume_level + 0.02))

    def volume_down(self) -> None:
        self.set_volume_level(max(0.0, self._attr_volume_level - 0.02))

    def mute_volume(self, mute: bool) -> None:
        if mute == self._attr_is_volume_muted:
            return
        if not self._client.toggle_mute(self._controller, self._zone):
            self._attr_available = False
            return
        self._attr_is_volume_muted = mute
        self._attr_available = True

    def select_source(self, source: str) -> None:
        if source not in self._attr_source_list:
            return
        self._apply_result(
            self._client.set_source(
                self._controller, self._zone, self._attr_source_list.index(source)
            ),
            "select source",
        )

    def _apply_result(self, status: dict | None, action: str) -> None:
        if status is None:
            self._attr_available = False
            _LOGGER.error("Failed to verify %s for controller %s zone %s", action, self._controller, self._zone)
            return
        self._apply_status(status)
