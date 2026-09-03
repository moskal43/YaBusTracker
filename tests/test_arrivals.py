"""A mixed list counts down without extra API requests or invented times."""

from datetime import UTC, datetime

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import configure


async def test_past_forecast_does_not_resurrect_event_from_schedule(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    events = stop_payload["data"]["transports"][0]["threads"][0]["BriefSchedule"][
        "Events"
    ]
    events[:] = [
        {"Estimated": {"value": 1788422300}, "Scheduled": {"value": 1788422700}}
    ]
    await configure(hass, http, stop_payload)
    state = hass.states.async_all("sensor")[0]
    assert state.attributes["arrivals"] == []
    assert state.attributes["status"] == "no_data"


async def test_three_sorted_arrivals_expire_without_polling(
    hass, http, stop_payload, freezer
):
    freezer.move_to("2026-09-03T08:00:00+00:00")
    stop_payload["data"]["transports"][0]["threads"][0]["BriefSchedule"]["Events"] = [
        {"Scheduled": {"value": 1788422640}},
        {"Estimated": {"value": 1788422430}, "Scheduled": {"value": 1788422450}},
        {"Estimated": {"value": "bad"}, "Scheduled": {"value": 1788422520}},
        {"Estimated": {"value": 1788422800}},
        {"Scheduled": {"value": 1788422000}},
    ]
    await configure(hass, http, stop_payload)
    state = hass.states.async_all("sensor")[0]
    assert state.attributes["arrivals"] == [
        {"timestamp": "2026-09-03T08:00:30+00:00", "source": "estimated"},
        {"timestamp": "2026-09-03T08:02:00+00:00", "source": "scheduled"},
        {"timestamp": "2026-09-03T08:04:00+00:00", "source": "scheduled"},
    ]
    request_count = sum(map(len, http.requests.values()))
    freezer.move_to("2026-09-03T08:00:31+00:00")
    async_fire_time_changed(hass, datetime(2026, 9, 3, 8, 0, 31, tzinfo=UTC))
    await hass.async_block_till_done()
    state = hass.states.get(state.entity_id)
    assert state.state == "2026-09-03T08:02:00+00:00"
    assert state.attributes["last_success"] == "2026-09-03T08:00:00+00:00"
    assert sum(map(len, http.requests.values())) == request_count
