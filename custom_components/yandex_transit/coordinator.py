"""One polling coordinator per stop, shared by every selected direction."""

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import MAX_INTERVAL
from .models import StopSnapshot, TransitError
from .runtime import Runtime

LOGGER = logging.getLogger(__name__)


class TransitCoordinator(DataUpdateCoordinator[StopSnapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime: Runtime):
        self.runtime = runtime
        self.stop_id = entry.data["stop_id"]
        self.stop_name = entry.data["stop_name"]
        self.interval = entry.options.get("scan_interval", entry.data["scan_interval"])
        if type(self.interval) is not int or not 60 <= self.interval <= MAX_INTERVAL:
            raise ConfigEntryError("Invalid scan interval: expected 60..86400 seconds")
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

    async def _async_update_data(self) -> StopSnapshot:
        if self._stopped:
            raise UpdateFailed("closed")
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
