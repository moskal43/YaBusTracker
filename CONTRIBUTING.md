# Contributing

Start with [development instructions](docs/development.md). Keep changes scoped
to bus arrivals and include a clear description of user-visible behavior.

- Keep transport data collection JSON-only. Do not add HTML scraping, browser
  automation, CAPTCHA solving, or another provider as a silent fallback.
- Keep HTTP asynchronous and bounded. Do not log cookies, tokens or signed URLs.
- Distinguish a valid empty response, request failure and a stale snapshot.
- Test observable HA behavior by controlling the external HTTP/DNS boundary and
  time; do not replace the integration's own client/coordinator in tests.
- Do not hardcode a city, stop, route, Home Assistant address or account.
- Include upstream notices for copied/adapted code.

Run the tests, Ruff and mypy before a pull request. CI additionally validates
the repository using HACS and Home Assistant hassfest.
