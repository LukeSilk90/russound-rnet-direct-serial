"""Protocol-level regression tests that do not require Home Assistant or hardware."""

import importlib.util
from pathlib import Path
import sys
import types

# Protocol-frame tests do not need real serial hardware or pyserial.
serial_stub = types.ModuleType("serial")
serial_stub.Serial = object
serial_stub.SerialException = Exception
serial_stub.EIGHTBITS = 8
serial_stub.PARITY_NONE = "N"
serial_stub.STOPBITS_ONE = 1
sys.modules.setdefault("serial", serial_stub)

MODULE = Path(__file__).parents[1] / "custom_components" / "russound_rnet_local" / "rnet.py"
spec = importlib.util.spec_from_file_location("rnet", MODULE)
rnet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rnet)


def test_power_on_frame_controller_1_zone_1():
    body = [0, 0, 0x7F, 0, 0, 0x70, 5, 2, 2, 0, 0, 0xF1, 0x23, 0, 1, 0, 0, 0, 1]
    assert rnet._build_frame(body).hex(" ") == (
        "f0 00 00 7f 00 00 70 05 02 02 00 00 f1 23 00 01 00 00 00 01 12 f7"
    )


def test_checksum_is_seven_bit():
    for size in range(1, 40):
        frame = rnet._build_frame([0x7F] * size)
        assert frame[-2] <= 0x7F
        assert frame[0] == 0xF0
        assert frame[-1] == 0xF7
