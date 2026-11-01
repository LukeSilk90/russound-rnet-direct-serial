# Russound RNET Direct Serial for Home Assistant

Control legacy Russound RNET multi-room amplifiers from Home Assistant over a
direct USB-to-RS232 connection. No `ser2net`, `socat`, TCP gateway or external
Russound Python package is required.

[![Validate](https://github.com/LukeSilk90/russound-rnet-direct-serial/actions/workflows/validate.yml/badge.svg)](https://github.com/LukeSilk90/russound-rnet-direct-serial/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![licence](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue.svg)](LICENSE)

## Why this exists

Home Assistant's built-in `russound_rnet` integration only connects over TCP, so
it needs a separate serial-to-network bridge running alongside it. This project
talks to the controller directly on the serial port and adds the things that
matter when a twenty-year-old amplifier is on the other end of the cable:
verified commands, automatic recovery and honest availability reporting.

| | Built-in `russound_rnet` | This integration |
|---|---|---|
| Connection | TCP gateway required | Direct USB serial |
| Setup | YAML | UI wizard |
| Command handling | Fire and forget | Verified by readback |
| Connection loss | Silent | Entities go unavailable |
| Recovery | Manual restart | Automatic, plus a reset action |
| Zones | 6 per platform block | Multiple linked controllers |
| Tone controls | No | Bass, treble, balance and more |
| Diagnostics | No | TX/RX counters, reconnects, last error |

## Features

- Direct serial connection with no bridge software.
- Guided UI setup and an options flow for renaming zones and sources.
- One media player per zone: power, source, volume and mute.
- Multiple linked controllers, six zones each.
- Bass, treble, balance and turn-on volume controls.
- Loudness, do-not-disturb and party-mode entities.
- Optional keypad backlight control for systems with UNO keypads.
- Commands confirmed by reading the controller back.
- Automatic reconnection and startup tolerance after a power cut.
- A `normalise_zone` action that flattens inherited installer tone settings.
- Connection health exposed as entity attributes.

## Project status

Version 1.1.0. The connection handling, power, source and volume control are
hardware-proven on a CAV6.6 system with a linked controller. The extended
parameter **reads** are validated against captured controller replies. The
extended parameter **writes** are implemented from the published protocol and
should be bench-verified on your own hardware before you rely on them; they use
a different RNET message type from the proven commands. Start with balance,
since a centre-to-hard-left change is immediately audible.

## Compatibility

| Controller | Status |
|---|---|
| CAV6.6 | Tested |
| Linked second controller, zones 7-12 | Tested |
| CAM6.6 | Expected, untested |
| CAA66 | Expected, untested. Usually needs a null-modem cable |
| CAS44 | Expected, untested |

Do-not-disturb and party mode are documented as unsupported on CAS44 and CAA66.
Those entities will log a warning and stay unavailable on such controllers.

Reports from other hardware are very welcome. Please open an issue.

## Origin and acknowledgement

The RNET framing and command approach derives from the GPL-licensed
[`laf/russound`](https://github.com/laf/russound) Python API, originally written
by Neil Lathwood and contributors, which was created to support Home Assistant's
original `russound_rnet` integration.

This project retains that lineage and is therefore released under
**GPL-3.0-or-later**. The direct serial transport, verified command handling,
automatic recovery, diagnostics, extended zone parameters, multi-controller
support and current Home Assistant integration were developed and tested by
Luke Silk.

This repository does not redistribute Russound protocol manuals.

## Installation

### HACS

1. In HACS, open **Integrations**.
2. From the overflow menu choose **Custom repositories**.
3. Add `https://github.com/LukeSilk90/russound-rnet-direct-serial` with category
   **Integration**.
4. Install **Russound RNET Direct Serial** and restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for
   **Russound RNET Direct Serial**.

### Manual

Copy `custom_components/russound_rnet_local` into your Home Assistant
`/config/custom_components/` directory, restart, then add the integration from
**Settings → Devices & services**.

## Setup wizard

The wizard asks for:

- **Serial port** — prefer a stable `/dev/serial/by-id/...` path. Find it under
  **Settings → System → Hardware → All hardware**.
- **Baud rate** — 19200 for RNET.
- **Linked controllers** — 1 for a single unit.
- **Zone names** — comma separated, applied in order, six per controller.
- **Source names** — comma separated, matching the **physical rear-panel source
  input numbers**.
- **Tone controls** — creates the bass, treble, balance and related entities.
- **Keypad controls** — only useful with UNO keypads. Off by default.

Setup fails cleanly if controller 1 zone 1 does not answer, so a miscabled
system is caught immediately rather than producing silent entities.

> **Source order matters.** The source list position must match the rear-panel
> input number. If the Denon is wired to Source 1 it must be first in the list.

## Hardware notes

- Use a **true RS-232 adaptor**, not a TTL UART cable. TTL cables enumerate
  identically but produce silence in both directions.
- Check whether your controller needs a **straight-through** or **null-modem**
  cable. A null-modem adaptor combined with a straight-through gender changer
  leaves the crossover in place, which also produces silence.
- The CAV6.6 has a **Front/Rear RS-232 selector** next to the DB-9. Only the
  selected socket is live.
- RNET is 19200 baud, 8 data bits, no parity, one stop bit, no flow control.
- With linked controllers, RS-232 goes to the master only. RNET Link carries
  control data between controllers, **not** source audio; wire analogue audio to
  each controller as the installation requires.

## Multi-controller mapping

| Controller | Home Assistant zones |
|---|---|
| 1 | 1-6 |
| 2 | 7-12 |
| 3 | 13-18 |

Each linked controller needs a unique Controller ID, set before linking, and
controller 1 should be the last unit powered on.

## Entities

Per zone:

| Entity | Type | Notes |
|---|---|---|
| Zone | `media_player` | Power, source, volume, mute |
| Bass | `number` | -10 to +10 |
| Treble | `number` | -10 to +10 |
| Balance | `number` | -10 left to +10 right |
| Turn-on volume | `number` | 0-100 in steps of 2 |
| Loudness | `switch` | |
| Do not disturb | `switch` | Unsupported on CAS44 and CAA66 |
| Party mode | `select` | off, on, master. Unsupported on CAS44 and CAA66 |
| Keypad backlight | `select` | Optional, disabled by default |

Read-only status appears as media-player attributes: `rnet_system_on`,
`rnet_shared_source`, `rnet_party_mode` and `rnet_do_not_disturb`.

### Polling design

One **All Zone Info** request returns power, source, volume, bass, treble,
loudness, balance, system-on, shared-source, party mode and do-not-disturb
together. A single coordinator poll per zone therefore feeds every entity, which
matters because RNET requires roughly 100 ms between messages. Turn-on volume and
keypad backlight are not in that reply, so they are fetched lazily and refreshed
after writes.

## Actions

### Reset the connection

```yaml
action: russound_rnet_local.reset_connection
```

Closes, reopens and validates the serial link, then refreshes all entities. Use
it if the zones go unavailable after a power cut. No Home Assistant restart is
needed.

### Normalise a zone

```yaml
action: russound_rnet_local.normalise_zone
data:
  controller: 1
  zone: 1
```

Sets bass, treble and balance flat and turns off loudness, do not disturb and
party mode. Useful when inheriting a system with unknown installer settings.

## Diagnostics

Every entity exposes:

| Attribute | Meaning |
|---|---|
| `serial_connected` | The port is open |
| `rnet_healthy` | Recent requests have been answered |
| `last_tx` / `last_rx` | Timestamps of the last send and valid reply |
| `tx_count` / `rx_count` | Byte counters |
| `consecutive_failures` | Failures since the last good reply |
| `reconnect_count` | Automatic recoveries performed |
| `last_serial_error` | Most recent error |

If `last_tx` advances while `last_rx` is stale, Home Assistant is transmitting
but receiving nothing, which points at cabling rather than software.

## Troubleshooting

**Setup fails with "cannot connect"** — confirm the serial path still exists,
check the cable type and the Front/Rear selector, and make sure no other process
is holding the port. Only one process can own a serial port at a time.

**Entities unavailable after a power cut** — the integration retries at startup
and reconnects automatically. If it does not recover, call
`russound_rnet_local.reset_connection`.

**Zone is on but silent** — check the zone is not muted, that its volume is
above zero, and that the source list order matches the physical input numbers.
Mute is a toggle in RNET and is not reported in the status reply, so Home
Assistant cannot read the true mute state back.

**A zone is much quieter than others** — check bass, treble and balance for
inherited installer settings, then call `normalise_zone`. If it persists across
all sources with a known-good speaker, suspect the amplifier channel.

**Tone controls do not respond** — these use a different RNET message type from
the proven commands. Enable debug logging and check whether the readback matches
what was written.

```yaml
logger:
  default: warning
  logs:
    custom_components.russound_rnet_local: debug
```

## Development

```bash
python -m compileall custom_components tests
ruff check custom_components tests
pytest -q
```

The protocol tests run without Home Assistant, pyserial or hardware, and include
regression checks against captured controller frames.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).

Russound product names and trademarks belong to their respective owners. This
project is independent and is not affiliated with or endorsed by Russound.
