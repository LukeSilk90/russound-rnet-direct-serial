# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-09-13

### Added
- Bass, treble, balance and turn-on volume `number` entities.
- Loudness and do-not-disturb `switch` entities.
- Party mode `select` entity, with off, on and master.
- Optional keypad backlight `select` entity, disabled by default.
- `normalise_zone` action to reset inherited installer tone settings.
- Read-only `rnet_system_on` and `rnet_shared_source` attributes.
- A polling coordinator so one request per zone feeds every entity.
- Per-zone devices in the device registry.
- Toggles in setup and options to enable or hide the extended controls.

### Changed
- The all-zone-info decode now returns all eleven documented fields.
- `_read_reply_locked` accepts a variable minimum length for short replies.

### Notes
- Extended parameter reads are validated against captured CAV6.6 replies.
- Extended parameter writes are implemented from the published protocol and
  await hardware verification. They use the RNET Set Data message type rather
  than the Event messages used by power, source and volume.
- Do not disturb and party mode are unsupported on CAS44 and CAA66.

## [1.0.0] - 2026-09-13

### Added
- Initial public release.
- Direct USB-to-RS232 RNET connection with no TCP serial bridge.
- UI configuration and options flows.
- One media player per zone with power, source, volume and mute.
- Multiple linked controllers, six zones each.
- Commands verified by reading the controller back.
- Automatic serial reconnection and startup probing.
- Unavailable-state handling and connection diagnostics.
- `reset_connection` action.
- HACS metadata, documentation, tests and a validation workflow.
