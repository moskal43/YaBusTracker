# Changelog

## 0.2.0

- Configurable sleep mode with local start and end times, including windows across midnight.
- No automatic source requests while sleeping; the next refresh is scheduled for wake time.
- Sensors expose `sleeping`, clear arrivals and preserve the next-attempt timestamp.
- Dashboard examples show a dedicated sleep message.

## 0.1.3

- Public GitHub repository and HACS custom-repository installation.
- Repository metadata, MIT license, attribution, issue templates and CI checks.
- Installation and update instructions, including migration from manual installation.
- Existing `yandex_transit` entries and entity IDs are preserved.

## 0.1.2

- Chosen bus-and-clock icon with a genuine transparent alpha channel and rounded edges.

## 0.1.1

- App renamed to YaBusTracker while preserving the existing technical integration domain.

## 0.1.0

- JSON-only asynchronous Yandex Maps client with in-memory cookies and CSRF handling.
- Configuration and options flows for multiple stops and route directions.
- Up to three arrivals per direction, with separate forecast/schedule sources.
- Expiry, freshness, shared backoff, Retry-After and cancellation on unload.
- Native Markdown card and English/Russian configuration translations.
