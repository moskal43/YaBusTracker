# Development

The test environment is pinned to Home Assistant Core 2026.8.3 and Python 3.14.
Create an isolated virtual environment:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m mypy custom_components/yandex_transit
.venv/bin/ruff check custom_components tests tools/build_release.py tools/build_brand.py
.venv/bin/python tools/build_release.py
```

Tests exercise real HA config/options flows, client, coordinator, sensors and
templates. HTTP/DNS and time are controlled. The cookie regression test uses a
local HTTP server to verify serialization on the wire, because request mocks
cannot detect cookie quoting changes performed later by aiohttp.

## Layout

- `api.py`: bounded JSON-only transport, token exchange, shared retry gate.
- `models.py`: strict stop validation and normalized arrivals/directions.
- `runtime.py`: integration-owned session and reference counting.
- `coordinator.py`: one stop snapshot shared by its selected routes.
- `config_flow.py`: stop setup, direction choice, options.
- `sensor.py`: timestamp, up to three arrivals, local expiry and diagnostics.
- `examples/dashboard.yaml`: native HA Markdown card.

Session tokens and cookies are memory-only. `CookieJar(quote_cookie=False)` is
intentional: quoting upstream cookie values caused repeated CSRF challenges in
live requests. Do not change it without running the wire-level regression test.

## Releases

Update both `manifest.json` and `pyproject.toml`, describe the changes in
`CHANGELOG.md`, and pass CI. Tag the tested commit with `v<version>`, build the
archive with `tools/build_release.py`, and publish a GitHub release. HACS uses
the repository's integration directory; the attached archive is also available
for manual installation.

GitHub Actions are pinned to reviewed commit IDs. When updating their pins or
development dependencies, run the complete validation workflow.

## Icon

`tools/build_brand.py` regenerates the selected transparent icon from
`design/source/icon-original.png` using Pillow. The master is stored under
`design/brand/`, and the 256×256 RGBA icon ships with the integration.
