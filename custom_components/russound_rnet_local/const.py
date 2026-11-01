"""Constants for the Russound RNET Direct Serial integration.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

DOMAIN = "russound_rnet_local"

PLATFORMS = ["media_player", "number", "switch", "select"]

CONF_BAUDRATE = "baudrate"
CONF_CONTROLLERS = "controllers"
CONF_ZONE_NAMES = "zone_names"
CONF_SOURCE_NAMES = "source_names"
CONF_ENABLE_TONE_CONTROLS = "enable_tone_controls"
CONF_ENABLE_KEYPAD_CONTROLS = "enable_keypad_controls"

DEFAULT_NAME = "Russound"
DEFAULT_BAUDRATE = 19200
DEFAULT_CONTROLLERS = 1
DEFAULT_ENABLE_TONE_CONTROLS = True
DEFAULT_ENABLE_KEYPAD_CONTROLS = False

ZONES_PER_CONTROLLER = 6
SOURCE_COUNT = 6

SERVICE_RESET_CONNECTION = "reset_connection"
SERVICE_NORMALISE_ZONE = "normalise_zone"

ATTR_CONTROLLER = "controller"
ATTR_ZONE = "zone"

SIGNAL_CONNECTION_RESET = f"{DOMAIN}_connection_reset"
