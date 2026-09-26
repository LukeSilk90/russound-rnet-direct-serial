"""Robust direct-serial client for the Russound RNET protocol.

Derived from the ``russound`` Python API originally written by Neil Lathwood
and contributors: https://github.com/laf/russound

Original work Copyright (c) 2014 Neil Lathwood and contributors.
Direct-serial transport, command verification, recovery and diagnostics
Copyright (c) 2026 Luke Silk and contributors.

This program is free software under the GNU General Public License, version 3
or, at your option, any later version. See the repository LICENSE file.
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

    def _read_reply_locked(self, signature: bytes) -> bytearray | None:
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
                if index != -1 and len(buffer) - index >= MIN_REPLY_LEN:
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
        return {
            "power": reply[11],
            "source": reply[12] + 1,
            "volume": reply[13] * 2,
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

