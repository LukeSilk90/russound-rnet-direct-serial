# Russound RNET Direct Serial for Home Assistant

A local Home Assistant custom integration for controlling legacy Russound RNET controllers directly through a USB-to-RS232 adaptor. No `ser2net`, `socat`, TCP gateway or external Russound Python package is required.

## Project status

Version 1.0.0 is the first public release candidate. It is hardware-tested on a CAV6.6 system with a linked controller, but the new UI config-entry packaging should be tested on the maintainer's Home Assistant installation before the GitHub release is marked stable.

## Features

- UI configuration flow
- One media-player entity per zone
- Multiple linked controllers, six zones per controller
- Power, source selection, volume and mute
- Two-way state polling and command verification
- Automatic serial reconnection and startup recovery
- Entities become unavailable when the controller stops responding
- Manual **Russound RNET Direct Serial: Reset connection** action
- Health attributes including last TX/RX, reconnect count and last serial error

## Tested hardware

- Russound CAV6.6 main controller
- Linked Russound controller exposing zones 7-12
- Prolific PL2303 USB-to-RS232 adaptor

Other RNET models may work because the implemented command subset is shared by CAS44, CAA66, CAM6.6 and CAV6.6 families, but community confirmation is needed.

## Origin and acknowledgement

The RNET framing and command approach is derived from the GPL-licensed [`laf/russound`](https://github.com/laf/russound) Python API originally written by Neil Lathwood and contributors. That package was created to support Home Assistant's original `russound_rnet` integration.

This project retains that lineage and is therefore released under **GPL-3.0-or-later**. The direct serial transport, verified command handling, automatic recovery, diagnostics, multi-controller config flow and current Home Assistant integration were substantially developed and tested.

This repository does not redistribute Russound protocol manuals.

## Installation with HACS

1. In HACS, open **Integrations**.
2. Add this repository as a custom repository with category **Integration**.
3. Install **Russound RNET Direct Serial**.
4. Restart Home Assistant.
5. Open **Settings > Devices & services > Add integration**.
6. Search for **Russound RNET Direct Serial** and follow the setup form.

## Migrating from the YAML prototype

1. Back up `/config/custom_components/russound_rnet_local`.
2. Remove or comment out the old `media_player: - platform: russound_rnet_local` YAML block.
3. Replace the old custom-component directory with this release.
4. Restart Home Assistant.
5. Add **Russound RNET Direct Serial** from **Settings > Devices & services**.
6. Enter the same serial path, controller count, zone names and source names.
7. Confirm the new entities work before deleting the backup.

Do not run `rnet_test.py` or other standalone serial tools while the integration is loaded, because only one process can own the serial port.

## Manual installation

Copy `custom_components/russound_rnet_local` into Home Assistant's `/config/custom_components/` directory, restart Home Assistant, then add the integration through **Settings > Devices & services**.

## Hardware

- Use a true RS-232 adaptor, not a TTL UART cable.
- Prefer a stable `/dev/serial/by-id/...` path.
- RNET serial settings are 19200 baud, 8 data bits, no parity, one stop bit and no flow control.
- Check the CAV6.6 Front/Rear RS-232 selector matches the socket in use.
- Confirm the required straight-through or null-modem wiring for the specific controller model.
- RNET Link carries control and source-specific IR signalling between controllers. Connect analogue source audio to each controller as required by the installation.

## Multi-controller mapping

- Controller 1: zones 1-6
- Controller 2: zones 7-12
- Controller 3: zones 13-18

Choose the number of linked controllers in the setup wizard. Zone and source names can be changed later in the integration options.

## Recovery and diagnostics

Call the action:

```yaml
action: russound_rnet_local.reset_connection
```

Each media-player entity exposes connection diagnostics such as `serial_connected`, `rnet_healthy`, `last_tx`, `last_rx`, `consecutive_failures`, `reconnect_count` and `last_serial_error`.

## Troubleshooting

### Integration cannot connect

- Stop any standalone RNET diagnostic script because only one process can own the serial port.
- Verify the selected serial path still exists.
- Check RS-232 cable type and the CAV6.6 port selector.
- Confirm Controller 1 Zone 1 responds at 19200 baud.

### UI changes but controller does not

This integration verifies power, source and volume changes through RNET readback. When verification fails, the entity becomes unavailable and the connection recovery logic runs.

### Mute behaviour

The implemented RNET mute control is a toggle. The regular all-zone status response does not expose mute state, so Home Assistant tracks mute locally after confirming that RNET remains responsive.

## Development

```bash
python -m compileall custom_components tests
ruff check custom_components tests
pytest -q
```

Hardware-in-the-loop testing is still required for serial recovery, multiple linked controllers and model compatibility.

## Licence

GPL-3.0-or-later. Russound product names and trademarks belong to their respective owners. This project is independent and is not affiliated with or endorsed by Russound.
