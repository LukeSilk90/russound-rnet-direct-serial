"""Tone, balance and turn-on volume controls.

The bass, treble and balance values come from the All Zone Info poll. Turn-on
volume is not in that reply, so it is fetched lazily on first use and cached.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_TONE_CONTROLS,
    CONF_ZONE_NAMES,
    DEFAULT_ENABLE_TONE_CONTROLS,
    ZONES_PER_CONTROLLER,
)
from .entity import RussoundZoneEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RussoundNumberDescription(NumberEntityDescription):
    """Describe a numeric Russound zone parameter."""

    data_key: str | None = None
    setter: str
    getter: str | None = None


NUMBERS: tuple[RussoundNumberDescription, ...] = (
    RussoundNumberDescription(
        key="bass",
        translation_key="bass",
        name="Bass",
        icon="mdi:music-clef-bass",
        native_min_value=-10,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        data_key="bass",
        setter="set_bass",
    ),
    RussoundNumberDescription(
        key="treble",
        translation_key="treble",
        name="Treble",
        icon="mdi:music-note",
        native_min_value=-10,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        data_key="treble",
        setter="set_treble",
    ),
    RussoundNumberDescription(
        key="balance",
        translation_key="balance",
        name="Balance",
        icon="mdi:pan-horizontal",
        native_min_value=-10,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        data_key="balance",
        setter="set_balance",
    ),
    RussoundNumberDescription(
        key="turn_on_volume",
        translation_key="turn_on_volume",
        name="Turn-on volume",
        icon="mdi:volume-medium",
        native_min_value=0,
        native_max_value=100,
        native_step=2,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        data_key=None,
        setter="set_turn_on_volume",
        getter="get_turn_on_volume",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create tone and level controls when enabled."""
    settings = {**entry.data, **entry.options}
    if not settings.get(CONF_ENABLE_TONE_CONTROLS, DEFAULT_ENABLE_TONE_CONTROLS):
        return

    runtime = entry.runtime_data
    entities = []
    for index, zone_name in enumerate(settings[CONF_ZONE_NAMES], start=1):
        controller = ((index - 1) // ZONES_PER_CONTROLLER) + 1
        zone = ((index - 1) % ZONES_PER_CONTROLLER) + 1
        entities.extend(
            RussoundNumber(
                runtime.coordinator, entry.entry_id, controller, zone, zone_name, description
            )
            for description in NUMBERS
        )
    async_add_entities(entities)


class RussoundNumber(RussoundZoneEntity, NumberEntity):
    """A numeric RNET zone parameter."""

    entity_description: RussoundNumberDescription

    def __init__(
        self, coordinator, entry_id, controller, zone, zone_name, description
    ) -> None:
        """Initialise the number entity."""
        super().__init__(coordinator, entry_id, controller, zone, zone_name)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}_{description.key}"
        self._cached: float | None = None

    @property
    def native_value(self) -> float | None:
        """Return the polled value, or the cached lazily fetched value."""
        if self.entity_description.data_key:
            value = self.zone_data.get(self.entity_description.data_key)
            return None if value is None else float(value)
        return self._cached

    async def async_added_to_hass(self) -> None:
        """Fetch parameters that the all-zone poll does not return."""
        await super().async_added_to_hass()
        if self.entity_description.getter:
            await self._async_refresh_cached()

    async def _async_refresh_cached(self) -> None:
        """Read a lazily fetched parameter from the controller."""
        getter: Callable = getattr(self.client, self.entity_description.getter)
        value = await self.hass.async_add_executor_job(
            getter, self._controller, self._zone
        )
        if value is not None:
            self._cached = float(value)
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Write the parameter and confirm it by reading it back."""
        setter: Callable = getattr(self.client, self.entity_description.setter)
        result = await self.hass.async_add_executor_job(
            setter, self._controller, self._zone, int(value)
        )
        if result is None:
            _LOGGER.error(
                "Failed to set %s on controller %s zone %s",
                self.entity_description.key,
                self._controller,
                self._zone,
            )
            return
        if self.entity_description.data_key:
            await self.coordinator.async_request_refresh()
        else:
            self._cached = float(result)
            self.async_write_ha_state()
