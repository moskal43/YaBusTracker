"""User-visible setup and arrivals, through real Home Assistant entities."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from .conftest import API


async def test_user_configures_stop_and_gets_first_arrival(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    http.get(API, payload={"csrfToken": "test-token"})
    http.get(API, payload=stop_payload, repeat=True)
    result = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": SOURCE_USER},
        data={
            "stop_url": "https://yandex.ru/maps/1/test/stops/stop__123/",
            "routes": "16",
            "scan_interval": 60,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    states = hass.states.async_all("sensor")
    assert len(states) == 1
    assert states[0].state == "2026-09-03T08:05:00+00:00"
    assert states[0].attributes["source"] == "estimated"
    assert states[0].attributes["direction"] == "Terminus"
    assert states[0].attributes["stop_name"] == "Test stop"
