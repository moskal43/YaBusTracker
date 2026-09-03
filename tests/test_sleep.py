"""Sleep mode suppresses polling in configurable local-time windows."""

from datetime import UTC, datetime, time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from homeassistant.helpers.template import Template

from custom_components.yandex_transit.coordinator import is_in_sleep_window

from .conftest import API, configure, refresh


@pytest.mark.parametrize(
    ("now", "start", "end", "expected"),
    [
        (time(22), time(22), time(6), True),
        (time(5, 59), time(22), time(6), True),
        (time(6), time(22), time(6), False),
        (time(12), time(10), time(14), True),
        (time(15), time(10), time(14), False),
    ],
)
def test_sleep_window_supports_midnight_and_daytime(now, start, end, expected):
    assert is_in_sleep_window(now, start, end) is expected


async def test_sleeping_setup_skips_poll_and_wakes_at_end(
    hass, http, stop_payload
):
    night = datetime(2026, 9, 3, 23, tzinfo=UTC)
    with patch(
        "custom_components.yandex_transit.coordinator.dt_util.now",
        return_value=night,
    ):
        result = await configure(
            hass,
            http,
            stop_payload,
            sleep_enabled=True,
            sleep_start="22:00:00",
            sleep_end="06:00:00",
        )
        entry = result["result"]
        state = hass.states.async_all("sensor")[0]

        assert entry.data["sleep_enabled"] is True
        assert entry.runtime_data.is_sleeping is True
        assert sum(map(len, http.requests.values())) == 2
        assert state.state == "unknown"
        assert state.attributes["status"] == "sleeping"
        assert state.attributes["arrivals"] == []
        assert state.attributes["source_available"] is False
        assert state.attributes["next_attempt"] == "2026-09-04T06:00:00+00:00"
        assert entry.runtime_data.update_interval.total_seconds() == 7 * 60 * 60
        card = yaml.safe_load(
            (Path(__file__).parents[1] / "examples/dashboard.yaml").read_text()
        )
        assert "Режим сна" in Template(card["content"], hass).async_render()

    http.get(API, payload=stop_payload, repeat=True)
    wake = datetime(2026, 9, 4, 6, tzinfo=UTC)
    with patch(
        "custom_components.yandex_transit.coordinator.dt_util.now",
        return_value=wake,
    ):
        await refresh(hass, state.entity_id)

    assert sum(map(len, http.requests.values())) == 3
    assert hass.states.get(state.entity_id).attributes["status"] == "no_data"


async def test_equal_sleep_times_are_rejected_without_request(hass, http):
    result = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": "user"},
        data={
            "stop_url": "https://yandex.ru/maps/1/test/stops/stop__123/",
            "routes": "16",
            "scan_interval": 60,
            "sleep_enabled": True,
            "sleep_start": "22:00:00",
            "sleep_end": "22:00:00",
        },
    )

    assert result["errors"] == {"base": "invalid_sleep_window"}
    assert not http.requests


async def test_sleep_window_can_be_changed_in_options(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    result = await configure(hass, http, stop_payload)
    entry = result["result"]
    http.get(API, payload=stop_payload, repeat=True)

    options = await hass.config_entries.options.async_init(
        entry.entry_id,
        data={
            "routes": "16",
            "scan_interval": 60,
            "sleep_enabled": True,
            "sleep_start": "23:30:00",
            "sleep_end": "05:45:00",
        },
    )
    await hass.async_block_till_done()

    assert options["type"] == "create_entry"
    assert entry.options["sleep_enabled"] is True
    assert entry.options["sleep_start"] == "23:30:00"
    assert entry.options["sleep_end"] == "05:45:00"
