"""Exercise the complete integration with only HTTP and time controlled."""

import inspect
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from aiohttp import ClientResponse
from aiohttp.client_proto import ResponseHandler
from aiohttp.streams import StreamReader
from aioresponses import aioresponses
from homeassistant.config_entries import SOURCE_USER
from homeassistant.setup import async_setup_component

pytest_plugins = ["pytest_homeassistant_custom_component"]
API = re.compile(r"https://yandex\.ru/maps/api/masstransit/getStopInfo\?.*")


@pytest.fixture
def hass_config_dir(tmp_path):
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).parents[1] / "custom_components", target_is_directory=True
    )
    return str(tmp_path)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def http():
    class CompatibleResponse(ClientResponse):
        """aioresponses 0.7.9 predates aiohttp 3.14's stream_writer argument."""

        def __init__(self, *args, **kwargs):
            if "stream_writer" in inspect.signature(ClientResponse).parameters:
                kwargs["stream_writer"] = SimpleNamespace(output_size=0)
            super().__init__(*args, **kwargs)

    class Responses(aioresponses):
        def get(self, url, **kwargs):
            super().get(url, response_class=CompatibleResponse, **kwargs)

    def stream_reader(loop):
        # The in-memory mock feeds the complete body before reading starts;
        # there is no socket/parser to pause when the normal high-water mark is hit.
        return StreamReader(ResponseHandler(loop=loop), limit=4_000_000, loop=loop)

    with (
        patch("aioresponses.core.stream_reader_factory", stream_reader),
        Responses() as responses,
    ):
        yield responses


@pytest.fixture
def stop_payload():
    return {
        "data": {
            "id": "stop__123",
            "name": "Test stop",
            "currentTime": 1788422400000,
            "transports": [
                {
                    "name": "16",
                    "type": "bus",
                    "lineId": "line16",
                    "threads": [
                        {
                            "threadId": "outbound",
                            "EssentialStops": [
                                {"name": "Terminus", "info": {"lastStop": True}}
                            ],
                            "BriefSchedule": {
                                "Events": [
                                    {
                                        "Estimated": {"value": 1788422700},
                                        "Scheduled": {"value": 1788422760},
                                    }
                                ]
                            },
                        }
                    ],
                }
            ],
        }
    }


async def configure(
    hass,
    http,
    payload,
    routes="16",
    interval=60,
    sleep_enabled=False,
    sleep_start="22:00:00",
    sleep_end="06:00:00",
):
    http.get(API, payload={"csrfToken": "test-token"})
    http.get(API, payload=payload)
    http.get(API, payload=payload)
    result = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": SOURCE_USER},
        data={
            "stop_url": f"https://yandex.ru/maps/1/test/stops/{payload['data']['id']}/",
            "routes": routes,
            "scan_interval": interval,
            "sleep_enabled": sleep_enabled,
            "sleep_start": sleep_start,
            "sleep_end": sleep_end,
        },
    )
    await hass.async_block_till_done()
    return result


async def refresh(hass, entity_id):
    await async_setup_component(hass, "homeassistant", {})
    await hass.services.async_call(
        "homeassistant", "update_entity", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()
