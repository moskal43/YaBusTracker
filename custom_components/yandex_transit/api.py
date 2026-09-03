"""Bounded JSON-only asynchronous access to the Yandex Maps stop API."""

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.util import dt as dt_util

from .const import ENDPOINT, MAX_RESPONSE_BYTES, REQUEST_TIMEOUT
from .models import StopSnapshot, TransitError, normalize


def signature(params: dict[str, str]) -> str:
    """Public DJB checksum (aioymaps, Copyright 2016 Ivan Belokobylskiy, MIT).

    See LICENSE in this integration directory for the retained license notice.
    """
    query = urlencode(dict(sorted(params.items(), key=lambda item: item[0].lower())))
    checksum = 5381
    for char in query:
        checksum = (checksum * 33 ^ ord(char)) & 0xFFFFFFFF
    return str(checksum)


def retry_delay(value: str | None) -> float:
    """Interpret Retry-After without retaining the response headers."""
    if not value:
        return 0
    try:
        if value.strip().isdigit():
            delay = float(value)
        else:
            date = parsedate_to_datetime(value)
            delay = (date - dt_util.utcnow()).total_seconds()
        return max(0, delay) if math.isfinite(delay) else 0
    except ValueError, TypeError, OverflowError:
        return 0


@dataclass
class RequestGate:
    """Non-secret service cooldown survives closing/reopening the HTTP session."""

    failures: int = 0
    deadline: float = 0.0
    next_attempt: datetime | None = None
    last_error: str | None = None


class TransitClient:
    """Serialize requests so a token exchange cannot race another stop."""

    def __init__(self, session: ClientSession, gate: RequestGate) -> None:
        self.session = session
        self._token: str | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self.gate = gate

    @property
    def next_attempt(self) -> datetime | None:
        return self.gate.next_attempt

    @property
    def last_error(self) -> str | None:
        return self.gate.last_error

    @property
    def remaining_pause(self) -> float:
        return max(0, self.gate.deadline - time.monotonic())

    async def async_close(self) -> None:
        async with self._lock:
            self._closed = True
            self._token = None
            self.session.cookie_jar.clear()
            self.session.detach()

    async def async_stop(self, stop_id: str, interval: int = 60) -> StopSnapshot:
        async with self._lock:
            if self._closed:
                raise TransitError("closed")
            if self.remaining_pause:
                raise TransitError(self.last_error or "retry_wait")
            try:
                result = await self._fetch_stop(stop_id)
            except TransitError as error:
                self.gate.failures += 1
                delay = max(
                    error.retry_after,
                    min(
                        interval * 2 ** min(self.gate.failures, 20), max(600, interval)
                    ),
                )
                self.gate.deadline = time.monotonic() + delay
                now = dt_util.utcnow()
                max_date = datetime.max.replace(tzinfo=UTC)
                self.gate.next_attempt = (
                    now + timedelta(seconds=delay)
                    if delay < (max_date - now).total_seconds()
                    else max_date
                )
                self.gate.last_error = str(error)
                raise
            self.gate.failures = 0
            self.gate.deadline = 0
            self.gate.next_attempt = None
            self.gate.last_error = None
            return result

    async def _fetch_stop(self, stop_id: str) -> StopSnapshot:
        params = {
            "ajax": "1",
            "id": stop_id,
            "uri": f"ymapsbm1://transit/stop?id={stop_id}",
            "lang": "ru",
            "locale": "ru_RU",
            "mode": "prognosis",
        }
        for _ in range(2):
            signed = dict(params)
            if self._token is not None:
                signed["csrfToken"] = self._token
                signed["s"] = signature(signed)
            payload = await self._request(signed)
            if (
                set(payload) == {"csrfToken"}
                and isinstance(payload["csrfToken"], str)
                and payload["csrfToken"]
            ):
                self._token = payload["csrfToken"]
                continue
            return normalize(payload.get("data"), stop_id, dt_util.utcnow())
        raise TransitError("session_error")

    async def _request(self, params: dict[str, str]) -> dict:
        try:
            async with self.session.get(
                ENDPOINT,
                params=params,
                allow_redirects=False,
                timeout=ClientTimeout(total=REQUEST_TIMEOUT),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "HomeAssistant-YaBusTracker/0.1",
                },
            ) as response:
                if response.status != 200:
                    raise TransitError(
                        f"http_{response.status}",
                        retry_delay(response.headers.get("Retry-After"))
                        if response.status == 429
                        else 0,
                    )
                if response.content_type != "application/json":
                    raise TransitError("non_json")
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise TransitError("response_too_large")
                try:
                    payload = json.loads(body)
                except ValueError, UnicodeError:
                    raise TransitError("invalid_json") from None
                if not isinstance(payload, dict):
                    raise TransitError("invalid_response")
                return payload
        except ClientError, TimeoutError:
            # Do not chain aiohttp exceptions: their URLs contain session tokens.
            raise TransitError("cannot_connect") from None
