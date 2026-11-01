"""Loudness and do-not-disturb switches.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
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
class RussoundSwitchDescription(SwitchEntityDescription):
    """Describe a boolean Russound zone parameter."""

    data_key: str
    setter: str


SWITCHES: tuple[RussoundSwitchDescription, ...] = (
    RussoundSwitchDescription(
        key="loudness",
        translation_key="loudness",
        name="Loudness",
        icon="mdi:ear-hearing",
        entity_category=EntityCategory.CONFIG,
        data_key="loudness",
        setter="set_loudness",
    ),
    RussoundSwitchDescription(
        key="do_not_disturb",
        translation_key="do_not_disturb",
        name="Do not disturb",
        icon="mdi:bell-off",
        entity_category=EntityCategory.CONFIG,
        data_key="do_not_disturb",
        setter="set_do_not_disturb",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the zone switches when tone controls are enabled."""
    settings = {**entry.data, **entry.options}
    if not settings.get(CONF_ENABLE_TONE_CONTROLS, DEFAULT_ENABLE_TONE_CONTROLS):
        return

    runtime = entry.runtime_data
    entities = []
    for index, zone_name in enumerate(settings[CONF_ZONE_NAMES], start=1):
        controller = ((index - 1) // ZONES_PER_CONTROLLER) + 1
        zone = ((index - 1) % ZONES_PER_CONTROLLER) + 1
        entities.extend(
            RussoundSwitch(
                runtime.coordinator, entry.entry_id, controller, zone, zone_name, description
            )
            for description in SWITCHES
        )
    async_add_entities(entities)


class RussoundSwitch(RussoundZoneEntity, SwitchEntity):
    """A boolean RNET zone parameter."""

    entity_description: RussoundSwitchDescription

    def __init__(
        self, coordinator, entry_id, controller, zone, zone_name, description
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, entry_id, controller, zone, zone_name)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{controller}_{zone}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the polled parameter state."""
        return self.zone_data.get(self.entity_description.data_key)

    async def _async_set(self, enabled: bool) -> None:
        """Write the parameter and refresh the coordinator."""
        setter: Callable = getattr(self.client, self.entity_description.setter)
        result = await self.hass.async_add_executor_job(
            setter, self._controller, self._zone, enabled
        )
        if result is None:
            _LOGGER.error(
                "Failed to set %s on controller %s zone %s. Note that do not "
                "disturb and party mode are not supported by CAS44 and CAA66.",
                self.entity_description.key,
                self._controller,
                self._zone,
            )
            return
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the parameter."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the parameter."""
        await self._async_set(False)
