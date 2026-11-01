# Contributing

Contributions are welcome, especially hardware reports for CAS44, CAA66 and
CAM6.6 controllers, which are currently untested.

## Reporting an issue

Please include:

- Home Assistant version
- controller model and firmware if known
- USB-to-RS232 adaptor chipset and cable type
- number of linked controllers
- relevant debug logs, with personal paths redacted

Enable debug logging first:

```yaml
logger:
  default: warning
  logs:
    custom_components.russound_rnet_local: debug
```

## Especially useful contributions

The extended zone parameter **writes** are implemented from the published
protocol but are not yet hardware-verified across models. Confirmation that
bass, treble, balance, turn-on volume, loudness, do not disturb, party mode or
keypad backlight work on your controller is genuinely valuable. Please include
the TX and RX hex frames from the debug log.

## Development

```bash
pip install pyserial pytest ruff
python -m compileall custom_components tests
ruff check custom_components tests
pytest -q
```

The protocol tests run without Home Assistant or hardware. If you change frame
construction or decoding, add a regression test, ideally with a captured frame.

## Licensing

Contributions are accepted under GPL-3.0-or-later. By submitting a contribution
you agree it may be distributed under that licence. Preserve the original
`laf/russound` attribution in protocol-derived files.

Do not add copyrighted Russound protocol manuals to the repository.
