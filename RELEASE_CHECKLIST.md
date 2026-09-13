# Version 1.0.0 release checklist

- [ ] Create `LukeSilk90/russound-rnet-direct-serial` as a public GitHub repository.
- [ ] Push the repository contents to the `main` branch.
- [ ] Confirm GitHub Actions passes.
- [ ] Add the repository to HACS as a custom integration.
- [ ] Back up the current YAML prototype.
- [ ] Remove the old YAML platform configuration.
- [ ] Install this repository version and restart Home Assistant.
- [ ] Complete the setup wizard using the stable `/dev/serial/by-id/...` path.
- [ ] Confirm all configured zones are created.
- [ ] Test power, source and volume readback on controller 1.
- [ ] Test linked-controller zones 7-12.
- [ ] Simulate loss of RNET response and confirm entities become unavailable.
- [ ] Run `russound_rnet_local.reset_connection` and confirm recovery.
- [ ] Confirm options can rename zones and sources.
- [ ] Capture UI screenshots for the README.
- [ ] Create GitHub release `v1.0.0`.
