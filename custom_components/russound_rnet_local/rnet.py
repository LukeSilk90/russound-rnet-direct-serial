"""Direct-serial client for the Russound RNET protocol.

Derived from the ``russound`` Python API originally written by Neil Lathwood
and contributors: https://github.com/laf/russound

Original work Copyright (c) 2014 Neil Lathwood and contributors.
Direct-serial transport, command verification, recovery, diagnostics and
extended zone parameters Copyright (c) 2026 Luke Silk and contributors.

This program is free software under the GNU General Public License, version 3
or, at your option, any later version. See the repository LICENSE file.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import serial


_LOGGER = logging.getLogger(__name__)

# RNET protocol constants
COMMAND_DELAY = 0.1
START_BYTE = 0xF0
END_BYTE = 0xF7
KEYPAD_ID = 0x70
BROADCAST = 0x7F
READ_ATTEMPTS = 10
MIN_REPLY_LEN = 24

# RNET zone parameter identifiers (Russound Controllers RNET protocol, section 8).
PARAM_BASS = 0x00
PARAM_TREBLE = 0x01
PARAM_LOUDNESS = 0x02
PARAM_BALANCE = 0x03
PARAM_TURN_ON_VOLUME = 0x04
PARAM_BACKGROUND_COLOUR = 0x05
PARAM_DO_NOT_DISTURB = 0x06
PARAM_PARTY_MODE = 0x07

# Tone/balance controls are transmitted as 0x00-0x14 and displayed as -10..+10.
TONE_OFFSET = 10
TONE_MIN = -10
TONE_MAX = 10

PARTY_MODES = {0: "off", 1: "on", 2: "master"}
PARTY_MODE_VALUES = {name: value for value, name in PARTY_MODES.items()}
BACKGROUND_COLOURS = {0: "off", 1: "amber", 2: "green"}
BACKGROUND_COLOUR_VALUES = {name: value for value, name in BACKGROUND_COLOURS.items()}

# Recovery behaviour
FAILURES_BEFORE_RECONNECT = 2
RECONNECT_DELAY = 1.0
RECONNECT_ATTEMPTS = 3
COMMAND_VERIFY_DELAY = 0.15
STARTUP_PROBE_ATTEMPTS = 12
STARTUP_PROBE_DELAY = 2.0


def _checksum(msg: list[int]) -> int:
    """Return the RNET checksum."""
    return (sum(msg) + len(msg)) & 0x7F


def _build_frame(body: list[int]) -> bytes:
    """Wrap a body with start byte, checksum and end byte."""
    msg = [START_BYTE, *body]
    msg.append(_checksum(msg))
    msg.append(END_BYTE)
    return bytes(msg)


def _clamp_tone(value: int) -> int:
    """Clamp a tone or balance value to the documented -10..+10 range."""
    return max(TONE_MIN, min(TONE_MAX, int(value)))


def _utc_iso(timestamp: float | None) -> str | None:
    """Convert a Unix timestamp to an HA-friendly UTC ISO string."""
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


class RussoundSerial:
    """Thread-safe blocking RNET client with reconnect and health tracking."""

    def __init__(self, port: str, baudrate: int = 19200) -> None:
        self._port = port
        self._baudrate = int(baudrate)
        self._serial: serial.Serial | None = None
        # RLock permits recovery helpers to be called while an operation holds the lock.
        self._lock = threading.RLock()
        self._last_send = 0.0
        self._last_tx_time: float | None = None
        self._last_rx_time: float | None = None
        self._consecutive_failures = 0
        self._reconnect_count = 0
        self._tx_count = 0
        self._rx_count = 0
        self._last_error: str | None = None

    @property
    def port(self) -> str:
        return self._port

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def is_healthy(self) -> bool:
        return self.is_connected and self._consecutive_failures < FAILURES_BEFORE_RECONNECT

    @property
    def diagnostics(self) -> dict:
        return {
            "serial_port": self._port,
            "serial_connected": self.is_connected,
            "rnet_healthy": self.is_healthy,
            "last_tx": _utc_iso(self._last_tx_time),
            "last_rx": _utc_iso(self._last_rx_time),
            "tx_count": self._tx_count,
            "rx_count": self._rx_count,
            "consecutive_failures": self._consecutive_failures,
            "reconnect_count": self._reconnect_count,
            "last_serial_error": self._last_error,
        }

    def connect(self) -> bool:
        """Open or reopen the serial port."""
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        self._close_locked()
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.2,
                write_timeout=2.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            # Give the USB UART a moment after opening, then discard stale boot noise.
            time.sleep(0.25)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._last_send = 0.0
            self._last_error = None
            _LOGGER.info("Opened Russound RNET serial port %s @ %s baud", self._port, self._baudrate)
            return True
        except (serial.SerialException, OSError) as err:
            self._serial = None
            self._last_error = str(err)
            _LOGGER.error("Could not open Russound serial port %s: %s", self._port, err)
            return False

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except (serial.SerialException, OSError):
                pass
            self._serial = None

    def _reconnect_locked(self, reason: str) -> bool:
        """Close and reopen the serial port, retrying a small number of times."""
        _LOGGER.warning("Reconnecting Russound serial port: %s", reason)
        self._last_error = reason
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            self._close_locked()
            time.sleep(RECONNECT_DELAY)
            if self._connect_locked():
                self._reconnect_count += 1
                _LOGGER.info("Russound serial reconnect succeeded on attempt %s", attempt)
                return True
            _LOGGER.warning("Russound serial reconnect attempt %s failed", attempt)
        _LOGGER.error("Russound serial reconnect failed after %s attempts", RECONNECT_ATTEMPTS)
        return False

    def _ensure_connected_locked(self) -> None:
        if not self.is_connected and not self._reconnect_locked("port is not open"):
            raise serial.SerialException("Russound serial port could not be opened")

    def _record_success_locked(self, received_bytes: int) -> None:
        self._last_rx_time = time.time()
        self._rx_count += received_bytes
        self._consecutive_failures = 0
        self._last_error = None

    def _record_failure_locked(self, reason: str) -> None:
        self._consecutive_failures += 1
        self._last_error = reason
        _LOGGER.warning(
            "Russound communication failure %s/%s: %s",
            self._consecutive_failures,
            FAILURES_BEFORE_RECONNECT,
            reason,
        )
        if self._consecutive_failures >= FAILURES_BEFORE_RECONNECT:
            self._reconnect_locked(reason)

    def _send_locked(self, frame: bytes) -> None:
        self._ensure_connected_locked()
        wait = COMMAND_DELAY - (time.monotonic() - self._last_send)
        if wait > 0:
            time.sleep(wait)
        try:
            assert self._serial is not None
            self._serial.write(frame)
            self._serial.flush()
            self._last_send = time.monotonic()
            self._last_tx_time = time.time()
            self._tx_count += len(frame)
            _LOGGER.debug("TX %s", frame.hex(" "))
        except (serial.SerialException, OSError) as err:
            self._record_failure_locked(f"write failed: {err}")
            raise

    def _read_reply_locked(
        self, signature: bytes, minimum_length: int = MIN_REPLY_LEN
    ) -> bytearray | None:
        """Read until a complete frame containing signature arrives."""
        if self._serial is None:
            return None
        buffer = bytearray()
        try:
            for _ in range(READ_ATTEMPTS):
                time.sleep(COMMAND_DELAY)
                waiting = self._serial.in_waiting
                if waiting:
                    buffer += self._serial.read(waiting)
                index = buffer.find(signature)
                if index != -1 and len(buffer) - index >= minimum_length:
                    reply = buffer[index:]
                    self._record_success_locked(len(reply))
                    _LOGGER.debug("RX %s", bytes(reply).hex(" "))
                    return reply
        except (serial.SerialException, OSError) as err:
            self._record_failure_locked(f"read failed: {err}")
            return None
        _LOGGER.debug("No RNET reply matching %s (buffer: %s)", signature.hex(" "), buffer.hex(" "))
        self._record_failure_locked("no matching RNET reply")
        return None

    def _get_zone_info_once_locked(self, controller: int, zone: int) -> dict | None:
        cc, zz = controller - 1, zone - 1
        request = _build_frame([
            cc, 0x00, BROADCAST, 0x00, 0x00, KEYPAD_ID,
            0x01, 0x04, 0x02, 0x00, zz, 0x07, 0x00, 0x00,
        ])
        signature = bytes([0x04, 0x02, 0x00, zz, 0x07])
        self._ensure_connected_locked()
        assert self._serial is not None
        self._serial.reset_input_buffer()
        self._send_locked(request)
        reply = self._read_reply_locked(signature)
        if reply is None:
            return None
        # Bytes 21-31 of the documented All Zone Info reply, relative to the
        # 04 02 00 zz 07 signature. Verified against captured CAV6.6 responses.
        return {
            "power": reply[11],
            "source": reply[12] + 1,
            "volume": reply[13] * 2,
            "bass": reply[14] - TONE_OFFSET,
            "treble": reply[15] - TONE_OFFSET,
            "loudness": bool(reply[16]),
            "balance": reply[17] - TONE_OFFSET,
            "system_on": bool(reply[18]),
            "shared_source": bool(reply[19]),
            "party_mode": PARTY_MODES.get(reply[20], "unknown"),
            "do_not_disturb": bool(reply[21]),
        }

    def get_zone_info(self, controller: int, zone: int, retry: bool = True) -> dict | None:
        """Read zone state. Reconnect and retry once when communication fails."""
        with self._lock:
            status = self._get_zone_info_once_locked(controller, zone)
            if status is not None or not retry:
                return status
            if not self._reconnect_locked(f"no status reply from controller {controller} zone {zone}"):
                return None
            return self._get_zone_info_once_locked(controller, zone)

    def wait_until_ready(self, controller: int = 1, zone: int = 1) -> bool:
        """Allow HA to start before the CAV6.6 has completed booting."""
        for attempt in range(1, STARTUP_PROBE_ATTEMPTS + 1):
            if self.get_zone_info(controller, zone, retry=True) is not None:
                _LOGGER.info("Russound responded to startup probe on attempt %s", attempt)
                return True
            _LOGGER.warning(
                "Russound not ready on startup probe %s/%s; retrying",
                attempt,
                STARTUP_PROBE_ATTEMPTS,
            )
            time.sleep(STARTUP_PROBE_DELAY)
        _LOGGER.error("Russound did not respond during startup probing; entities will start unavailable")
        return False
        
    def manual_recover(self, controller: int = 1, zone: int = 1) -> bool:
        """Manually close, reopen and validate the RNET serial connection."""

        _LOGGER.warning("Manual Russound connection recovery requested")

        with self._lock:
            # Clear the previous failure state before performing a clean reconnect.
            self._consecutive_failures = 0

            if not self._reconnect_locked("manual recovery requested"):
                _LOGGER.error(
                    "Manual Russound recovery could not reopen the serial port"
                )
                return False

        # Do not hold the serial lock during the startup retry delays.
        if self.wait_until_ready(controller, zone):
            _LOGGER.info(
                "Manual Russound recovery succeeded using controller %s zone %s",
                controller,
                zone,
            )
            return True

        _LOGGER.error(
            "Manual Russound recovery reopened the port, but controller %s "
            "zone %s did not respond",
            controller,
            zone,
        )

        return False
        
    def _verified_command(
        self,
        body: list[int],
        controller: int,
        zone: int,
        predicate,
        description: str,
    ) -> dict | None:
        """Send a command, read status, and retry once after reconnect if unverified."""
        command = _build_frame(body)
        for attempt in (1, 2):
            with self._lock:
                try:
                    self._ensure_connected_locked()
                    assert self._serial is not None
                    self._serial.reset_input_buffer()
                    self._send_locked(command)
                except (serial.SerialException, OSError) as err:
                    _LOGGER.warning("%s attempt %s write failed: %s", description, attempt, err)
                time.sleep(COMMAND_VERIFY_DELAY)
                status = self._get_zone_info_once_locked(controller, zone)
                if status is not None and predicate(status):
                    _LOGGER.debug("Verified %s: %s", description, status)
                    return status
                _LOGGER.warning("Could not verify %s on attempt %s; status=%s", description, attempt, status)
                if attempt == 1:
                    self._reconnect_locked(f"command verification failed: {description}")
        return None

    def set_power(self, controller: int, zone: int, power: int) -> dict | None:
        cc, zz = controller - 1, zone - 1
        requested = 1 if power else 0
        body = [cc, 0x00, BROADCAST, 0x00, 0x00, KEYPAD_ID, 0x05, 0x02, 0x02, 0x00,
                0x00, 0xF1, 0x23, 0x00, requested, 0x00, zz, 0x00, 0x01]
        return self._verified_command(
            body, controller, zone,
            lambda status: status["power"] == requested,
            f"power={requested} controller={controller} zone={zone}",
        )

    def set_volume(self, controller: int, zone: int, volume: int) -> dict | None:
        cc, zz = controller - 1, zone - 1
        requested = max(0, min(100, int(volume)))
        # RNET resolution is 2%, so compare against the quantised value.
        expected = (requested // 2) * 2
        body = [cc, 0x00, BROADCAST, 0x00, 0x00, KEYPAD_ID, 0x05, 0x02, 0x02, 0x00,
                0x00, 0xF1, 0x21, 0x00, requested // 2, 0x00, zz, 0x00, 0x01]
        return self._verified_command(
            body, controller, zone,
            lambda status: status["volume"] == expected,
            f"volume={expected} controller={controller} zone={zone}",
        )

    def set_source(self, controller: int, zone: int, source: int) -> dict | None:
        cc, zz = controller - 1, zone - 1
        requested_zero_based = int(source)
        expected_one_based = requested_zero_based + 1
        body = [cc, 0x00, BROADCAST, 0x00, zz, KEYPAD_ID, 0x05, 0x02, 0x00, 0x00,
                0x00, 0xF1, 0x3E, 0x00, 0x00, 0x00, requested_zero_based, 0x00, 0x01]
        return self._verified_command(
            body, controller, zone,
            lambda status: status["source"] == expected_one_based,
            f"source={expected_one_based} controller={controller} zone={zone}",
        )

    def toggle_mute(self, controller: int, zone: int) -> bool:
        """Toggle mute. Status frame does not expose mute, so verify link health only."""
        cc, zz = controller - 1, zone - 1
        body = [cc, 0x00, BROADCAST, 0x00, zz, KEYPAD_ID, 0x05, 0x02, 0x02, 0x00,
                0x00, 0xF1, 0x40, 0x00, 0x00, 0x00, 0x0D, 0x00, 0x01]
        command = _build_frame(body)
        for attempt in (1, 2):
            with self._lock:
                try:
                    self._ensure_connected_locked()
                    assert self._serial is not None
                    self._serial.reset_input_buffer()
                    self._send_locked(command)
                except (serial.SerialException, OSError):
                    pass
                time.sleep(COMMAND_VERIFY_DELAY)
                if self._get_zone_info_once_locked(controller, zone) is not None:
                    return True
                if attempt == 1:
                    self._reconnect_locked("mute command health verification failed")
        return False

    def all_on_off(self, power: int) -> bool:
        """Send all-on/all-off and confirm at least controller 1 zone 1 responds."""
        body = [BROADCAST, 0x00, BROADCAST, 0x00, 0x00, KEYPAD_ID, 0x05, 0x02, 0x02,
                0x00, 0x00, 0xF1, 0x22, 0x00, 0x00, int(bool(power)), 0x00, 0x00, 0x01]
        command = _build_frame(body)
        with self._lock:
            self._ensure_connected_locked()
            self._send_locked(command)
        time.sleep(COMMAND_VERIFY_DELAY)
        return self.get_zone_info(1, 1, retry=True) is not None

    # ------------------------------------------------------------------
    # Extended zone parameters
    #
    # These use the RNET "Set Data" (0x00) and "Request Data" (0x01) message
    # types with a five-level target path, rather than the Event (0x05)
    # messages used by power, source and volume.
    #
    # NOTE: the read path is validated against captured CAV6.6 All Zone Info
    # replies. The write path is implemented from the published protocol and
    # should be bench-verified per controller model.
    # ------------------------------------------------------------------

    def _parameter_request_frame(self, controller: int, zone: int, param: int) -> bytes:
        """Build a Request Data frame for a single zone parameter."""
        cc, zz = controller - 1, zone - 1
        return _build_frame(
            [cc, 0x00, BROADCAST, cc, zz, KEYPAD_ID,
             0x01, 0x05, 0x02, 0x00, zz, 0x00, int(param), 0x00, 0x00, 0x00]
        )

    def _parameter_set_frame(
        self, controller: int, zone: int, param: int, value: int
    ) -> bytes:
        """Build a Set Data frame for a single zone parameter."""
        cc, zz = controller - 1, zone - 1
        return _build_frame(
            [cc, 0x00, BROADCAST, cc, zz, KEYPAD_ID,
             0x00, 0x05, 0x02, 0x00, zz, 0x00, int(param),
             0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, int(value)]
        )

    def _read_parameter_once_locked(
        self, controller: int, zone: int, param: int
    ) -> int | None:
        """Read one raw parameter value. The lock must already be held."""
        zz = zone - 1
        signature = bytes([0x05, 0x02, 0x00, zz, 0x00, int(param)])
        self._ensure_connected_locked()
        assert self._serial is not None
        self._serial.reset_input_buffer()
        self._send_locked(self._parameter_request_frame(controller, zone, param))
        reply = self._read_reply_locked(signature, minimum_length=13)
        if reply is None:
            return None
        return reply[12]

    def get_zone_parameter(
        self, controller: int, zone: int, param: int, retry: bool = True
    ) -> int | None:
        """Read a raw zone parameter value, reconnecting once on failure."""
        with self._lock:
            value = self._read_parameter_once_locked(controller, zone, param)
            if value is not None or not retry:
                return value
            if not self._reconnect_locked(
                f"no parameter reply from controller {controller} zone {zone}"
            ):
                return None
            return self._read_parameter_once_locked(controller, zone, param)

    def set_zone_parameter(
        self, controller: int, zone: int, param: int, value: int
    ) -> int | None:
        """Set a zone parameter and confirm it by reading the value back."""
        frame = self._parameter_set_frame(controller, zone, param, value)
        description = (
            f"parameter 0x{param:02x}={value} controller={controller} zone={zone}"
        )
        for attempt in (1, 2):
            with self._lock:
                try:
                    self._ensure_connected_locked()
                    assert self._serial is not None
                    self._serial.reset_input_buffer()
                    self._send_locked(frame)
                except (serial.SerialException, OSError) as err:
                    _LOGGER.warning("%s attempt %s write failed: %s", description, attempt, err)
                time.sleep(COMMAND_VERIFY_DELAY)
                readback = self._read_parameter_once_locked(controller, zone, param)
                if readback == value:
                    _LOGGER.debug("Verified %s", description)
                    return readback
                _LOGGER.warning(
                    "Could not verify %s on attempt %s; read back %s",
                    description, attempt, readback,
                )
                if attempt == 1:
                    self._reconnect_locked(f"parameter verification failed: {description}")
        return None

    # -- friendly wrappers --------------------------------------------------

    def set_bass(self, controller: int, zone: int, level: int) -> int | None:
        """Set bass between -10 and +10. Returns the displayed level."""
        raw = self.set_zone_parameter(
            controller, zone, PARAM_BASS, _clamp_tone(level) + TONE_OFFSET
        )
        return None if raw is None else raw - TONE_OFFSET

    def set_treble(self, controller: int, zone: int, level: int) -> int | None:
        """Set treble between -10 and +10. Returns the displayed level."""
        raw = self.set_zone_parameter(
            controller, zone, PARAM_TREBLE, _clamp_tone(level) + TONE_OFFSET
        )
        return None if raw is None else raw - TONE_OFFSET

    def set_balance(self, controller: int, zone: int, position: int) -> int | None:
        """Set balance from -10 (left) through 0 (centre) to +10 (right)."""
        raw = self.set_zone_parameter(
            controller, zone, PARAM_BALANCE, _clamp_tone(position) + TONE_OFFSET
        )
        return None if raw is None else raw - TONE_OFFSET

    def set_loudness(self, controller: int, zone: int, enabled: bool) -> bool | None:
        """Enable or disable loudness compensation."""
        raw = self.set_zone_parameter(
            controller, zone, PARAM_LOUDNESS, 1 if enabled else 0
        )
        return None if raw is None else bool(raw)

    def set_do_not_disturb(self, controller: int, zone: int, enabled: bool) -> bool | None:
        """Enable or disable do not disturb.

        Not supported by CAS44 and CAA66 controllers.
        """
        raw = self.set_zone_parameter(
            controller, zone, PARAM_DO_NOT_DISTURB, 1 if enabled else 0
        )
        return None if raw is None else bool(raw)

    def set_turn_on_volume(self, controller: int, zone: int, volume: int) -> int | None:
        """Set the power-on volume, 0-100 in steps of 2."""
        requested = max(0, min(100, int(volume)))
        raw = self.set_zone_parameter(
            controller, zone, PARAM_TURN_ON_VOLUME, requested // 2
        )
        return None if raw is None else raw * 2

    def set_party_mode(self, controller: int, zone: int, mode: str) -> str | None:
        """Set party mode to off, on or master.

        Not supported by CAS44 and CAA66 controllers.
        """
        if mode not in PARTY_MODE_VALUES:
            raise ValueError(f"Unknown party mode: {mode}")
        raw = self.set_zone_parameter(
            controller, zone, PARAM_PARTY_MODE, PARTY_MODE_VALUES[mode]
        )
        return None if raw is None else PARTY_MODES.get(raw)

    def set_background_colour(self, controller: int, zone: int, colour: str) -> str | None:
        """Set the keypad backlight colour to off, amber or green.

        Only affects systems with UNO keypads attached.
        """
        if colour not in BACKGROUND_COLOUR_VALUES:
            raise ValueError(f"Unknown background colour: {colour}")
        raw = self.set_zone_parameter(
            controller, zone, PARAM_BACKGROUND_COLOUR, BACKGROUND_COLOUR_VALUES[colour]
        )
        return None if raw is None else BACKGROUND_COLOURS.get(raw)

    def get_turn_on_volume(self, controller: int, zone: int) -> int | None:
        """Read the power-on volume as a 0-100 percentage."""
        raw = self.get_zone_parameter(controller, zone, PARAM_TURN_ON_VOLUME)
        return None if raw is None else raw * 2

    def get_background_colour(self, controller: int, zone: int) -> str | None:
        """Read the keypad backlight colour."""
        raw = self.get_zone_parameter(controller, zone, PARAM_BACKGROUND_COLOUR)
        return None if raw is None else BACKGROUND_COLOURS.get(raw)

    def normalise_zone(self, controller: int, zone: int) -> dict[str, bool]:
        """Reset inherited installer tone settings to neutral values.

        Sets bass, treble and balance flat, disables loudness and do not
        disturb, and clears party mode. Returns a per-parameter result map so
        callers can report partial success on controllers that do not support
        every parameter.
        """
        results: dict[str, bool] = {}
        results["bass"] = self.set_bass(controller, zone, 0) is not None
        results["treble"] = self.set_treble(controller, zone, 0) is not None
        results["balance"] = self.set_balance(controller, zone, 0) is not None
        results["loudness"] = self.set_loudness(controller, zone, False) is not None
        results["do_not_disturb"] = (
            self.set_do_not_disturb(controller, zone, False) is not None
        )
        results["party_mode"] = self.set_party_mode(controller, zone, "off") is not None
        _LOGGER.info(
            "Normalised controller %s zone %s: %s", controller, zone, results
        )
        return results
