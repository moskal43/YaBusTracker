"""Cookie values must reach the wire in the form accepted by the JSON API."""

import socket

from aiohttp import web
from homeassistant.config_entries import SOURCE_USER


async def test_cookie_value_is_not_requoted_on_wire(
    hass, aiohttp_server, socket_enabled, monkeypatch, stop_payload, freezer
):
    from custom_components.yandex_transit import api

    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [
            {
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
        ]

    monkeypatch.setattr("aiohttp.resolver.AsyncResolver.resolve", resolve)

    freezer.move_to("2026-09-03T08:00:00+00:00")
    accepted = []

    async def stop(request):
        cookie_ok = request.headers.get("Cookie") == "session=fixture+value=="
        if cookie_ok and request.query.get("csrfToken") == "test-token":
            accepted.append(True)
            return web.json_response(stop_payload)
        response = web.json_response({"csrfToken": "test-token"})
        response.headers.add("Set-Cookie", "session=fixture+value==; Path=/")
        return response

    app = web.Application()
    app.router.add_get("/stop", stop)
    server = await aiohttp_server(app, access_log=None)
    monkeypatch.setattr(
        api, "ENDPOINT", str(server.make_url("/stop").with_host("localhost"))
    )
    result = await hass.config_entries.flow.async_init(
        "yandex_transit",
        context={"source": SOURCE_USER},
        data={
            "stop_url": "https://yandex.ru/maps/1/test/stops/stop__123/",
            "routes": "16",
            "scan_interval": 60,
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.async_all("sensor")[0].state == "2026-09-03T08:05:00+00:00"
    assert len(accepted) == 2
