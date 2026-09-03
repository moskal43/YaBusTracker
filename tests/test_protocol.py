"""Protocol failures remain observable without exposing upstream secrets."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from aiohttp import ClientConnectionError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import API, configure, refresh


@pytest.mark.parametrize(
    "response,error",
    [
        (
            {"status": 302, "headers": {"Location": "https://example.org/captcha"}},
            "http_302",
        ),
        (
            {
                "status": 200,
                "content_type": "text/html",
                "body": "<html>captcha</html>",
            },
            "non_json",
        ),
        ({"body": "{broken"}, "invalid_json"),
        ({"payload": {"data": {"id": "foreign-stop"}}}, "invalid_response"),
        (
            {
                "payload": {
                    "data": {
                        "id": "stop__123",
                        "currentTime": 1788422400000,
                        "name": "Test",
                        "transports": {},
                    }
                }
            },
            "invalid_response",
        ),
        ({"body": "x" * 2_000_001}, "response_too_large"),
        ({"exception": ClientConnectionError("secret-token-in-url")}, "cannot_connect"),
        ({"timeout": True}, "cannot_connect"),
    ],
)
async def test_bad_response_clears_forecast_with_safe_diagnostics(
    hass, http, stop_payload, freezer, caplog, response, error
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    await configure(hass, http, stop_payload)
    entity_id = hass.states.async_all("sensor")[0].entity_id
    http.get(API, **response)
    await refresh(hass, entity_id)
    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes["status"] == "error"
    assert state.attributes["arrivals"] == []
    assert state.attributes["last_error"] == error
    assert state.attributes["next_attempt"] == "2026-09-03T08:02:00+00:00"
    assert "secret-token-in-url" not in caplog.text


async def test_token_rotation_has_one_retry_and_shared_pause_across_stops(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    first = await configure(hass, http, stop_payload)
    second_payload = deepcopy(stop_payload)
    second_payload["data"].update(id="stop__456", name="Second stop")
    second = await configure(hass, http, second_payload)
    first_id = next(
        s.entity_id
        for s in hass.states.async_all("sensor")
        if s.attributes["stop_id"] == "stop__123"
    )
    second_id = next(
        s.entity_id
        for s in hass.states.async_all("sensor")
        if s.attributes["stop_id"] == "stop__456"
    )
    assert hass.states.get(second_id).attributes["stop_name"] == "Second stop"
    before = sum(map(len, http.requests.values()))
    http.get(API, payload={"csrfToken": "rotated-one"})
    http.get(API, payload={"csrfToken": "rotated-two"})
    await asyncio.gather(refresh(hass, first_id), refresh(hass, second_id))
    assert sum(map(len, http.requests.values())) == before + 2
    assert hass.states.get(first_id).attributes["status"] == "error"
    assert hass.states.get(second_id).attributes["status"] == "error"
    assert await hass.config_entries.async_unload(first["result"].entry_id)
    assert "yandex_transit" in hass.data
    assert await hass.config_entries.async_unload(second["result"].entry_id)
    count = sum(map(len, http.requests.values()))
    freezer.move_to("2026-09-03T08:20:00+00:00")
    async_fire_time_changed(hass, datetime(2026, 9, 3, 8, 20, tzinfo=UTC))
    await hass.async_block_till_done()
    assert sum(map(len, http.requests.values())) == count
    assert "yandex_transit" not in hass.data


async def test_initial_setup_failure_keeps_entity_and_recovers_automatically(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    entry = MockConfigEntry(
        domain="yandex_transit",
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
    http.get(API, status=503)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = hass.states.async_all("sensor")[0].entity_id
    assert hass.states.get(entity_id).attributes["last_success"] is None
    assert hass.states.get(entity_id).attributes["status"] == "error"
    http.get(API, payload=stop_payload)
    freezer.move_to("2026-09-03T08:02:01+00:00")
    async_fire_time_changed(hass, datetime(2026, 9, 3, 8, 2, 1, tzinfo=UTC))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "2026-09-03T08:05:00+00:00"
