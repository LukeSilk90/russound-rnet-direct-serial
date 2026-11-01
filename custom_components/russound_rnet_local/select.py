"""Party mode and keypad backlight selects.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_KEYPAD_CONTROLS,
    CONF_ENABLE_TONE_CONTROLS,
    CONF_ZONE_NAMES,
    DEFAULT_ENABLE_KEYPAD_CONTROLS,
    DEFAULT_ENABLE_TONE_CONTROLS,
    ZONES_PER_CONTROLLER,
)
from .entity import RussoundZoneEntity

_LOGGER = logging.getLogger(__name__)

PARTY_OPTIONS = ["off", "on", "master"]
COLOUR_OPTIONS = ["off", "amber", "green"]


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create party-mode and optional keypad backlight selects."""
    settings = {**entry.data, **entry.options}
    tone_enabled = settings.get(CONF_ENABLE_TONE_CONTROLS, DEFAULT_ENABLE_TONE_CONTROLS)
    keypad_enabled = settings.get(
        CONF_ENABLE_KEYPAD_CONTROLS, DEFAULT_ENABLE_KEYPAD_CONTROLS
    )
    if not tone_enabled and not keypad_enabled:
        return

    runtime = entry.runtime_data
    entities = []
    for index, zone_name in enumerate(settings[CONF_ZONE_NAMES], start=1):
        controller = ((index - 1) // ZONES_PER_CONTROLLER) + 1
        zone = ((index - 1) % ZONES_PER_CONTROLLER) + 1
        if tone_enabled:
            entities.append(
                RussoundPartyModeSelect(
                    runtime.coordinator, entry.entry_id, controller, zone, zone_name
                )
            )
        if keypad_enabled:
            entities.append(
                RussoundBackgroundColourSelect(
                    runtime.coordinator, entry.entry_id, controller, zone, zone_name
                )
            )
    async_add_entities(entities)


class RussoundPartyModeSelect(RussoundZoneEntity, SelectEntity):
    """Party mode: off, on or master.

    Not supported by CAS44 and CAA66 controllers.
    """

    _attr_translation_key = "party_mode"
    _attr_name = "Party mode"
    _attr_icon = "mdi:party-popper"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = PARTY_OPTIONS

    def __init__(self, coordinator, entry_id, controller, zone, zone_name) -> None:
        """Initialise the party mode select."""
        super().__init__(coordinator, entry_id, controller, zone, zone_name)
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}_party_mode"

    @property
    def current_option(self) -> str | None:
        """Return the polled party mode."""
        value = self.zone_data.get("party_mode")
        return value if value in PARTY_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        """Set party mode."""
        result = await self.hass.async_add_executor_job(
            self.client.set_party_mode, self._controller, self._zone, option
        )
        if result is None:
            _LOGGER.error(
                "Failed to set party mode on controller %s zone %s. Party mode "
                "is not supported by CAS44 and CAA66 controllers.",
                self._controller,
                self._zone,
            )
            return
        await self.coordinator.async_request_refresh()


class RussoundBackgroundColourSelect(RussoundZoneEntity, SelectEntity):
    """Keypad backlight colour.

    Only meaningful on systems with UNO keypads attached. The value is not part
    of the all-zone poll, so it is fetched lazily and cached.
    """

    _attr_translation_key = "background_colour"
    _attr_name = "Keypad backlight"
    _attr_icon = "mdi:lightbulb-on-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = COLOUR_OPTIONS
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry_id, controller, zone, zone_name) -> None:
        """Initialise the backlight select."""
        super().__init__(coordinator, entry_id, controller, zone, zone_name)
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}_background_colour"
        self._cached: str | None = None

    @property
    def current_option(self) -> str | None:
        """Return the cached backlight colour."""
        return self._cached

    async def async_added_to_hass(self) -> None:
        """Read the current backlight colour once on startup."""
        await super().async_added_to_hass()
        value = await self.hass.async_add_executor_job(
            self.client.get_background_colour, self._controller, self._zone
        )
        if value is not None:
            self._cached = value
            self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Set the keypad backlight colour."""
        result = await self.hass.async_add_executor_job(
            self.client.set_background_colour, self._controller, self._zone, option
        )
        if result is None:
            _LOGGER.error(
                "Failed to set keypad backlight on controller %s zone %s",
                self._controller,
                self._zone,
            )
            return
        self._cached = result
        self.async_write_ha_state()
