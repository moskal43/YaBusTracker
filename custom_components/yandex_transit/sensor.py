"""Timestamp sensors expose arrivals with their individual data sources."""

from collections.abc import Callable
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import TransitConfigEntry
from .coordinator import TransitCoordinator
from .models import entity_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TransitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    selections = entry.options.get("selections", entry.data["selections"])
    async_add_entities(
        TransitSensor(entry.runtime_data, selected) for selected in selections
    )


class TransitSensor(CoordinatorEntity[TransitCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: TransitCoordinator, selected: dict[str, str]):
        super().__init__(coordinator)
        self.selected = selected
        self._cancel_expiry: Callable[[], None] | None = None
        self._attr_unique_id = entity_unique_id(coordinator.stop_id, selected)
        self._attr_name = (
            f"{coordinator.stop_name} {selected['route']} → {selected['direction']}"
        )

    @property
    def available(self):
        # HA omits extra attributes on unavailable entities. Keep the local
        # sensor available with an unknown timestamp and explicit source status,
        # preserving last_success and the distinction between empty and failed.
        return True

    @property
    def source_status(self):
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            return "error"
        if dt_util.utcnow() >= self.coordinator.data.received_at + timedelta(
            seconds=2 * self.coordinator.interval
        ):
            return "stale"
        return "ok"

    def _arrivals(self):
        if self.source_status != "ok":
            return ()
        for direction in self.coordinator.data.directions:
            if (
                direction.line_id == self.selected["line_id"]
                and direction.thread_id == self.selected["thread_id"]
            ):
                return tuple(
                    a for a in direction.arrivals if a.timestamp > dt_util.utcnow()
                )[:3]
        return ()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._schedule_expiry()

    async def async_will_remove_from_hass(self):
        if self._cancel_expiry:
            self._cancel_expiry()
            self._cancel_expiry = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self):
        super()._handle_coordinator_update()
        self._schedule_expiry()

    @callback
    def _schedule_expiry(self):
        if self._cancel_expiry:
            self._cancel_expiry()
            self._cancel_expiry = None
        arrivals = self._arrivals()
        deadlines = [a.timestamp for a in arrivals[:1]]
        if self.coordinator.data is not None:
            stale_at = self.coordinator.data.received_at + timedelta(
                seconds=2 * self.coordinator.interval
            )
            if stale_at > dt_util.utcnow():
                deadlines.append(stale_at)
        if deadlines:
            self._cancel_expiry = async_track_point_in_utc_time(
                self.hass, self._expire, min(deadlines)
            )

    @callback
    def _expire(self, now):
        self._cancel_expiry = None
        self.async_write_ha_state()
        self._schedule_expiry()

    @property
    def native_value(self):
        arrivals = self._arrivals()
        return arrivals[0].timestamp if arrivals else None

    @property
    def extra_state_attributes(self):
        arrivals = self._arrivals()
        snapshot = self.coordinator.data
        status = self.source_status
        return {
            "stop_id": self.coordinator.stop_id,
            "stop_name": self.coordinator.stop_name,
            **self.selected,
            "source": arrivals[0].source if arrivals else None,
            "arrivals": [
                {"timestamp": a.timestamp.isoformat(), "source": a.source}
                for a in arrivals
            ],
            "last_success": snapshot.received_at.isoformat() if snapshot else None,
            "last_error": self.coordinator.last_error,
            "next_attempt": self.coordinator.next_attempt.isoformat()
            if self.coordinator.next_attempt
            else None,
            "source_available": status == "ok",
            "status": status if status != "ok" else ("ok" if arrivals else "no_data"),
        }
