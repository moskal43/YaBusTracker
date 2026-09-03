"""Reference-count the integration's private cookie jar across entries and flows."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiohttp import CookieJar
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import RequestGate, TransitClient
from .const import DOMAIN


@dataclass
class Runtime:
    client: TransitClient
    users: int = 0
    cancel_stop_listener: Callable[[], None] | None = None


def acquire(hass: HomeAssistant) -> Runtime:
    if DOMAIN not in hass.data:
        session = async_create_clientsession(
            # Yandex returns unquoted values containing base64 padding. Adding
            # quotes when sending them back causes another CSRF challenge.
            hass,
            auto_cleanup=False,
            cookie_jar=CookieJar(quote_cookie=False),
        )
        gate = hass.data.setdefault(f"{DOMAIN}_request_gate", RequestGate())
        runtime = Runtime(TransitClient(session, gate))

        async def stop(event):
            await runtime.client.async_close()

        runtime.cancel_stop_listener = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, stop
        )
        hass.data[DOMAIN] = runtime
    runtime = hass.data[DOMAIN]
    runtime.users += 1
    return runtime


async def release(hass: HomeAssistant, runtime: Runtime) -> None:
    runtime.users -= 1
    if runtime.users == 0:
        hass.data.pop(DOMAIN, None)
        if runtime.cancel_stop_listener:
            runtime.cancel_stop_listener()
        await runtime.client.async_close()


@asynccontextmanager
async def borrow(hass: HomeAssistant):
    runtime = acquire(hass)
    try:
        yield runtime.client
    finally:
        await release(hass, runtime)
