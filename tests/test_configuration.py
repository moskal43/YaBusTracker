"""Configuration, disambiguation, shared polling and entry lifecycle."""

from copy import deepcopy

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from .conftest import API, configure


async def test_group_stop_link_configures_another_stop(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    stop_payload["data"].update(id="group__3280", name="Another stop")
    result = await configure(hass, http, stop_payload)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert hass.states.async_all("sensor")[0].attributes["stop_id"] == "group__3280"


@pytest.mark.parametrize("interval", [0, 59, True, 10**15])
async def test_invalid_interval_is_rejected_without_request(hass, http, interval):
    result = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": SOURCE_USER},
        data={
            "stop_url": "https://yandex.ru/maps/1/test/stops/stop__123/",
            "routes": "16",
            "scan_interval": interval,
        },
    )
    assert result["errors"] == {"base": "invalid_interval"}
    assert not http.requests


async def test_multiple_routes_options_keep_identity_and_remove_old_entities(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    second = deepcopy(stop_payload["data"]["transports"][0])
    second.update(name="22А", lineId="line22")
    stop_payload["data"]["transports"].append(second)
    result = await configure(hass, http, stop_payload, routes="16, 22А")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    states = hass.states.async_all("sensor")
    assert {s.attributes["route"] for s in states} == {"16", "22А"}
    survivor_id = next(s.entity_id for s in states if s.attributes["route"] == "22А")
    assert (
        sum(map(len, http.requests.values())) == 3
    )  # one setup snapshot for both routes

    duplicate = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": SOURCE_USER},
        data={
            "stop_url": "https://yandex.ru/maps/1/test/stops/stop__123/",
            "routes": "16",
            "scan_interval": 60,
        },
    )
    assert duplicate["reason"] == "already_configured"
    assert sum(map(len, http.requests.values())) == 3

    http.get(API, payload=stop_payload, repeat=True)
    options = await hass.config_entries.options.async_init(
        entry.entry_id, data={"routes": "22А", "scan_interval": 120}
    )
    assert options["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    states = hass.states.async_all("sensor")
    assert [s.entity_id for s in states] == [survivor_id]
    assert entry.options["scan_interval"] == 120
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "yandex_transit" not in hass.data


async def test_ambiguous_number_requires_explicit_direction(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    other = deepcopy(stop_payload["data"]["transports"][0])
    other["lineId"] = "other-line"
    other["threads"][0]["EssentialStops"][0]["name"] = "Other terminus"
    stop_payload["data"]["transports"].append(other)
    result = await configure(hass, http, stop_payload)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "select"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"directions": ['["other-line","outbound"]']}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    states = hass.states.async_all("sensor")
    assert len(states) == 1
    assert states[0].attributes["direction"] == "Other terminus"
