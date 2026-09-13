# Contributing

Contributions are welcome, particularly hardware reports for CAS44, CAA66, CAM6.6 and CAV6.6 controllers.

When reporting an issue, include:

- Home Assistant version
- controller model and firmware if known
- USB-to-RS232 adaptor chipset
- cable type
- number of linked controllers
- relevant integration logs with personal paths redacted if necessary

Run the local checks before opening a pull request:

```bash
python -m compileall custom_components tests
ruff check custom_components tests
pytest -q
```

Do not include copyrighted Russound protocol manuals in the repository. Protocol-derived implementation and references may be documented, but redistribution rights for manuals must be respected.

## Licensing

Contributions are accepted under GPL-3.0-or-later. By submitting a contribution, you agree that it may be distributed under that licence. Preserve the original `laf/russound` attribution in protocol-derived files.
