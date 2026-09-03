"""Cancellation and reconfiguration cannot leave polling or bypass a cooldown."""

import asyncio
from datetime import UTC, datetime

from aioresponses import CallbackResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import API, configure, refresh


async def test_options_reload_does_not_bypass_shared_retry_after(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    result = await configure(hass, http, stop_payload)
    entry = result["result"]
    entity_id = hass.states.async_all("sensor")[0].entity_id
    http.get(API, status=429, headers={"Retry-After": "3600"})
    await refresh(hass, entity_id)
    calls = sum(map(len, http.requests.values()))
    options = await hass.config_entries.options.async_init(
        entry.entry_id, data={"routes": "16", "scan_interval": 120}
    )
    assert options["type"] == "create_entry"
    await hass.async_block_till_done()
    assert sum(map(len, http.requests.values())) == calls
    state = hass.states.get(entity_id)
    assert state.attributes["next_attempt"] == "2026-09-03T09:00:00+00:00"
    assert state.attributes["status"] == "error"
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to("2026-09-03T08:30:00+00:00")
    http.get(API, payload=stop_payload)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert sum(map(len, http.requests.values())) == calls


async def test_unload_cancels_active_request_and_keeps_ha_session(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    result = await configure(hass, http, stop_payload)
    entity_id = hass.states.async_all("sensor")[0].entity_id
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def slow_response(url, **kwargs):
        started.set()
        await blocked.wait()
        return CallbackResult(payload=stop_payload)

    http.get(API, callback=slow_response)
    request = asyncio.create_task(refresh(hass, entity_id))
    await asyncio.wait_for(started.wait(), 2)
    assert await hass.config_entries.async_unload(result["result"].entry_id)
    await asyncio.gather(request, return_exceptions=True)
    assert "yandex_transit" not in hass.data
    assert not async_get_clientsession(hass).closed
    calls = sum(map(len, http.requests.values()))
    freezer.move_to("2026-09-03T09:00:00+00:00")
    async_fire_time_changed(hass, datetime(2026, 9, 3, 9, tzinfo=UTC))
    await hass.async_block_till_done()
    assert sum(map(len, http.requests.values())) == calls
