"""One polling coordinator per stop, shared by every selected direction."""

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SLEEP_ENABLED,
    CONF_SLEEP_END,
    CONF_SLEEP_START,
    DEFAULT_SLEEP_END,
    DEFAULT_SLEEP_START,
    MAX_INTERVAL,
)
from .models import StopSnapshot, TransitError
from .runtime import Runtime

LOGGER = logging.getLogger(__name__)


def is_in_sleep_window(now: time, start: time, end: time) -> bool:
    """Return whether local wall time is inside a non-equal sleep window."""
    if start < end:
        return start <= now < end
    return now >= start or now < end


class TransitCoordinator(DataUpdateCoordinator[StopSnapshot | None]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime: Runtime):
        self.runtime = runtime
        self.stop_id = entry.data["stop_id"]
        self.stop_name = entry.data["stop_name"]
        self.interval = entry.options.get("scan_interval", entry.data["scan_interval"])
        if type(self.interval) is not int or not 60 <= self.interval <= MAX_INTERVAL:
            raise ConfigEntryError("Invalid scan interval: expected 60..86400 seconds")
        current = entry.options or entry.data
        self.sleep_enabled = current.get(CONF_SLEEP_ENABLED, False)
        if type(self.sleep_enabled) is not bool:
            raise ConfigEntryError("Invalid sleep mode setting")
        try:
            self.sleep_start = time.fromisoformat(
                current.get(CONF_SLEEP_START, DEFAULT_SLEEP_START)
            )
            self.sleep_end = time.fromisoformat(
                current.get(CONF_SLEEP_END, DEFAULT_SLEEP_END)
            )
        except (TypeError, ValueError) as error:
            raise ConfigEntryError("Invalid sleep window") from error
        if self.sleep_start == self.sleep_end:
            raise ConfigEntryError("Invalid sleep window: start and end must differ")
        self.last_error: str | None = None
        self.next_attempt: datetime | None = None
        self._active_request: asyncio.Task[StopSnapshot] | None = None
        self._stopped = False
        super().__init__(
            hass,
            LOGGER,
            name=f"YaBusTracker {self.stop_id}",
            config_entry=entry,
            update_interval=timedelta(seconds=self.interval),
        )

    @property
    def is_sleeping(self) -> bool:
        if not self.sleep_enabled:
            return False
        return is_in_sleep_window(
            dt_util.now().time().replace(tzinfo=None), self.sleep_start, self.sleep_end
        )

    def _sleep_wake(self) -> datetime:
        now = dt_util.now()
        wake = datetime.combine(now.date(), self.sleep_end, tzinfo=now.tzinfo)
        if wake <= now:
            wake += timedelta(days=1)
        return wake

    async def _async_update_data(self) -> StopSnapshot | None:
        if self._stopped:
            raise UpdateFailed("closed")
        if self.is_sleeping:
            wake = self._sleep_wake()
            self.last_error = None
            self.next_attempt = dt_util.as_utc(wake)
            self.update_interval = max(timedelta(seconds=1), wake - dt_util.now())
            return self.data
        self._active_request = self.hass.async_create_task(
            self.runtime.client.async_stop(self.stop_id, self.interval)
        )
        try:
            result = await self._active_request
        except TransitError as error:
            self.last_error = str(error)
            self.next_attempt = self.runtime.client.next_attempt
            # Long Retry-After remains enforced by the client; a local daily
            # wake-up avoids overflowing timedelta/OS timer limits.
            self.update_interval = timedelta(
                seconds=min(86400, max(1, self.runtime.client.remaining_pause))
            )
            raise UpdateFailed(str(error)) from None
        finally:
            self._active_request = None
        self.last_error = None
        self.next_attempt = dt_util.utcnow() + timedelta(seconds=self.interval)
        self.update_interval = timedelta(seconds=self.interval)
        return result

    async def async_shutdown(self) -> None:
        self._stopped = True
        if self._active_request is not None:
            self._active_request.cancel()
            with suppress(asyncio.CancelledError):
                await self._active_request
        await super().async_shutdown()
