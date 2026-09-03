"""Render the shipped native card with Home Assistant's actual template engine."""

from pathlib import Path

import yaml
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .conftest import API, configure, refresh


async def test_card_renders_mixed_sources_and_failure_without_old_times(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:01+00:00")
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Kirov"))
    events = stop_payload["data"]["transports"][0]["threads"][0]["BriefSchedule"][
        "Events"
    ]
    events.append({"Scheduled": {"value": 1788422760}})
    await configure(hass, http, stop_payload)
    card = yaml.safe_load(
        (Path(__file__).parents[1] / "examples/dashboard.yaml").read_text()
    )
    template = Template(card["content"], hass)
    rendered = template.async_render()
    assert "Через 5 мин" in rendered
    assert "11:05" in rendered
    assert "по расписанию" in rendered
    assert "прогноз" in rendered
    assert "Обновлено: 03.09 11:00:01" in rendered
    http.get(API, status=503)
    await refresh(hass, "sensor.test_stop_16_terminus")
    rendered = template.async_render()
    assert "Не удалось обновить" in rendered
    assert "Через" not in rendered


async def test_interval_only_data_displays_no_data(hass, http, stop_payload, freezer):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    thread = stop_payload["data"]["transports"][0]["threads"][0]
    thread["BriefSchedule"] = {
        "Intervals": [{"from": "08:00", "to": "09:00", "interval": 10}]
    }
    await configure(hass, http, stop_payload)
    state = hass.states.async_all("sensor")[0]
    assert state.state == "unknown"
    assert state.attributes["status"] == "no_data"
    assert state.attributes["arrivals"] == []
