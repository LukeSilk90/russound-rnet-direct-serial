"""Protocol regression tests.

These run without Home Assistant, pyserial or real hardware. The captured
frames come from a live Russound CAV6.6 controller.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

# The protocol module imports pyserial at module scope. Frame construction and
# decoding do not touch the serial port, so a stub keeps the tests dependency free.
_serial_stub = types.ModuleType("serial")
_serial_stub.Serial = object
_serial_stub.SerialException = Exception
_serial_stub.EIGHTBITS = 8
_serial_stub.PARITY_NONE = "N"
_serial_stub.STOPBITS_ONE = 1
sys.modules.setdefault("serial", _serial_stub)

_MODULE = (
    Path(__file__).parents[1]
    / "custom_components"
    / "russound_rnet_local"
    / "rnet.py"
)
_spec = importlib.util.spec_from_file_location("rnet", _MODULE)
rnet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rnet)


def _hex(text: str) -> bytes:
    """Build a byte string from space separated hex."""
    return bytes(int(part, 16) for part in text.split())


# Captured from a real CAV6.6, controller 1 zone 1, before and after a
# power-on plus volume change to 40 percent.
CAPTURED_BEFORE = _hex(
    "f0 00 00 70 00 00 7f 00 00 04 02 00 00 07 00 00 01 00 0c 00 00 00 0a "
    "11 10 01 0a 00 00 00 00 00 4f f7"
)
CAPTURED_AFTER = _hex(
    "f0 00 00 70 00 00 7f 00 00 04 02 00 00 07 00 00 01 00 0c 00 01 00 14 "
    "11 10 01 0a 01 00 00 00 00 5b f7"
)


def _decode(reply: bytes, zone: int = 1) -> dict:
    """Decode an All Zone Info reply using the shipped byte offsets."""
    signature = bytes([0x04, 0x02, 0x00, zone - 1, 0x07])
    body = reply[reply.find(signature):]
    return {
        "power": body[11],
        "source": body[12] + 1,
        "volume": body[13] * 2,
        "bass": body[14] - rnet.TONE_OFFSET,
        "treble": body[15] - rnet.TONE_OFFSET,
        "loudness": bool(body[16]),
        "balance": body[17] - rnet.TONE_OFFSET,
        "system_on": bool(body[18]),
        "shared_source": bool(body[19]),
        "party_mode": rnet.PARTY_MODES.get(body[20]),
        "do_not_disturb": bool(body[21]),
    }


def test_power_on_frame_is_unchanged():
    """The proven power-on frame must never regress."""
    body = [0, 0, 0x7F, 0, 0, 0x70, 5, 2, 2, 0, 0, 0xF1, 0x23, 0, 1, 0, 0, 0, 1]
    assert rnet._build_frame(body).hex(" ") == (
        "f0 00 00 7f 00 00 70 05 02 02 00 00 f1 23 00 01 00 00 00 01 12 f7"
    )


def test_status_request_frame_is_unchanged():
    """The proven zone status request must never regress."""
    body = [0, 0, 0x7F, 0, 0, 0x70, 1, 4, 2, 0, 0, 7, 0, 0]
    assert rnet._build_frame(body).hex(" ") == (
        "f0 00 00 7f 00 00 70 01 04 02 00 00 07 00 00 7c f7"
    )


def test_checksum_is_seven_bit_and_framed():
    """Every frame must start 0xF0, end 0xF7 and carry a 7-bit checksum."""
    for size in range(1, 40):
        frame = rnet._build_frame([0x7F] * size)
        assert frame[0] == 0xF0
        assert frame[-1] == 0xF7
        assert frame[-2] <= 0x7F
        assert frame[-2] == (sum(frame[:-2]) + len(frame[:-2])) & 0x7F


def test_decode_matches_captured_hardware_reply():
    """The extended decode must match a real controller response."""
    before = _decode(CAPTURED_BEFORE)
    after = _decode(CAPTURED_AFTER)

    assert before["power"] == 0
    assert before["volume"] == 20
    assert after["power"] == 1
    assert after["volume"] == 40

    # Inherited installer tone settings, identical in both captures.
    for decoded in (before, after):
        assert decoded["source"] == 1
        assert decoded["bass"] == 7
        assert decoded["treble"] == 6
        assert decoded["loudness"] is True
        assert decoded["balance"] == 0
        assert decoded["shared_source"] is False
        assert decoded["party_mode"] == "off"
        assert decoded["do_not_disturb"] is False

    # system_on flips precisely when the zone is powered, which confirms the
    # byte alignment rather than a coincidental match.
    assert before["system_on"] is False
    assert after["system_on"] is True


def test_parameter_frames_are_well_formed():
    """Set and request frames must be valid and carry the parameter id."""
    client = rnet.RussoundSerial.__new__(rnet.RussoundSerial)

    set_frame = client._parameter_set_frame(1, 1, rnet.PARAM_BALANCE, 10)
    assert set_frame[0] == 0xF0 and set_frame[-1] == 0xF7
    assert set_frame[-2] == (sum(set_frame[:-2]) + len(set_frame[:-2])) & 0x7F
    assert set_frame[7] == 0x00  # Set Data message type
    assert set_frame[13] == rnet.PARAM_BALANCE

    get_frame = client._parameter_request_frame(1, 1, rnet.PARAM_BASS)
    assert get_frame[0] == 0xF0 and get_frame[-1] == 0xF7
    assert get_frame[-2] == (sum(get_frame[:-2]) + len(get_frame[:-2])) & 0x7F
    assert get_frame[7] == 0x01  # Request Data message type
    assert get_frame[13] == rnet.PARAM_BASS


def test_parameter_frames_encode_zone_and_controller():
    """Controller and zone must be zero based on the wire."""
    client = rnet.RussoundSerial.__new__(rnet.RussoundSerial)
    frame = client._parameter_set_frame(2, 4, rnet.PARAM_TREBLE, 10)
    assert frame[1] == 1  # controller 2 -> 0x01
    assert frame[5] == 3  # zone 4 -> 0x03
    assert frame[11] == 3


def test_tone_values_are_clamped():
    """Out of range tone values must clamp to the documented limits."""
    assert rnet._clamp_tone(50) == rnet.TONE_MAX
    assert rnet._clamp_tone(-50) == rnet.TONE_MIN
    assert rnet._clamp_tone(0) == 0


def test_party_and_colour_lookups_round_trip():
    """Named options must map cleanly to and from wire values."""
    for name, value in rnet.PARTY_MODE_VALUES.items():
        assert rnet.PARTY_MODES[value] == name
    for name, value in rnet.BACKGROUND_COLOUR_VALUES.items():
        assert rnet.BACKGROUND_COLOURS[value] == name
