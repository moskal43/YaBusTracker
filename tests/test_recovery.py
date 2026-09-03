"""State and outbound request timing under failure and recovery."""

from datetime import UTC, datetime

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import API, configure, refresh


@pytest.mark.parametrize("retry_after", ["180", "Thu, 03 Sep 2026 08:03:00 GMT"])
async def test_rate_limit_hides_old_arrivals_and_waits_before_recovery(
    hass, http, stop_payload, freezer, retry_after
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    await configure(hass, http, stop_payload)
    entity_id = hass.states.async_all("sensor")[0].entity_id
    http.get(API, status=429, headers={"Retry-After": retry_after})
    await refresh(hass, entity_id)
    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes["arrivals"] == []
    assert state.attributes["status"] == "error"
    assert state.attributes["last_success"] == "2026-09-03T08:00:00+00:00"
    assert state.attributes["next_attempt"] == "2026-09-03T08:03:00+00:00"
    calls = sum(map(len, http.requests.values()))
    freezer.move_to("2026-09-03T08:02:59+00:00")
    await refresh(hass, entity_id)
    assert sum(map(len, http.requests.values())) == calls
    freezer.move_to("2026-09-03T08:03:00+00:00")
    http.get(API, payload=stop_payload)
    async_fire_time_changed(hass, datetime(2026, 9, 3, 8, 3, tzinfo=UTC))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "2026-09-03T08:05:00+00:00"
    assert hass.states.get(entity_id).attributes["last_error"] is None


async def test_snapshot_expires_even_when_polling_is_disabled(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    entry = MockConfigEntry(
        domain="yandex_transit",
        pref_disable_polling=True,
        data={
            "stop_id": "stop__123",
            "stop_name": "Test stop",
            "scan_interval": 60,
            "selections": [
                {
                    "line_id": "line16",
                    "thread_id": "outbound",
                    "route": "16",
                    "direction": "Terminus",
                }
            ],
        },
    )
    entry.add_to_hass(hass)
    http.get(API, payload=stop_payload)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = hass.states.async_all("sensor")[0].entity_id
    freezer.move_to("2026-09-03T08:02:01+00:00")
    async_fire_time_changed(hass, datetime(2026, 9, 3, 8, 2, 1, tzinfo=UTC))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    assert hass.states.get(entity_id).attributes["status"] == "stale"
    assert hass.states.get(entity_id).attributes["arrivals"] == []
