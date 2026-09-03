"""Normalized stop snapshots; upstream JSON stays outside HA entities."""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


class TransitError(Exception):
    """A safe, bounded error code suitable for HA logs and diagnostics."""

    def __init__(self, code: str, retry_after: float = 0):
        super().__init__(code)
        self.retry_after = retry_after


def stop_id_from_url(value: str) -> str:
    """Extract an ID locally; never navigate to user-supplied URLs."""
    try:
        url = urlparse(value.strip())
        if (
            url.scheme != "https"
            or url.hostname not in {"yandex.ru", "yandex.com", "maps.yandex.ru"}
            or url.username
            or url.password
            or url.port not in (None, 443)
        ):
            raise ValueError
        match = re.fullmatch(
            r"/maps/(?:[^/]+/)*stops/((?:stop|group)__[A-Za-z0-9_-]+)/?", url.path
        )
        if not match:
            raise ValueError
        return match[1]
    except ValueError, AttributeError:
        raise TransitError("invalid_url") from None


@dataclass(frozen=True)
class Arrival:
    timestamp: datetime
    source: str


@dataclass(frozen=True)
class Direction:
    line_id: str
    thread_id: str
    route: str
    name: str
    arrivals: tuple[Arrival, ...]

    @property
    def key(self) -> str:
        # JSON tuple encoding avoids delimiter collisions in upstream IDs.
        return json.dumps([self.line_id, self.thread_id], separators=(",", ":"))

    def selection(self) -> dict[str, str]:
        return {
            "line_id": self.line_id,
            "thread_id": self.thread_id,
            "route": self.route,
            "direction": self.name,
        }


@dataclass(frozen=True)
class StopSnapshot:
    stop_id: str
    name: str
    received_at: datetime
    server_time: datetime
    directions: tuple[Direction, ...]


def entity_unique_id(stop_id: str, selected: dict[str, str]) -> str:
    return json.dumps(
        [stop_id, selected["line_id"], selected["thread_id"]], separators=(",", ":")
    )


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or not 946684800 <= seconds < 4102444800:
            return None
        return datetime.fromtimestamp(seconds, UTC)
    except ValueError, OverflowError, OSError:
        return None


def normalize(data: Any, stop_id: str, now: datetime) -> StopSnapshot:
    """Validate the stop envelope and normalize boardable bus directions."""
    if not isinstance(data, dict) or data.get("id") != stop_id:
        raise TransitError("invalid_response")
    try:
        server_time = _timestamp(float(data["currentTime"]) / 1000)
    except KeyError, TypeError, ValueError, OverflowError:
        server_time = None
    if server_time is None or not isinstance(data.get("name"), str):
        raise TransitError("invalid_response")
    transports = data.get("transports")
    if not isinstance(transports, list):
        raise TransitError("invalid_response")
    directions = []
    for transport in transports:
        if not isinstance(transport, dict):
            raise TransitError("invalid_response")
        if transport.get("type") != "bus":
            continue
        if not isinstance(transport.get("threads"), list):
            raise TransitError("invalid_response")
        for thread in transport["threads"]:
            if not isinstance(thread, dict):
                raise TransitError("invalid_response")
            if thread.get("noBoarding"):
                continue
            line_id, thread_id = transport.get("lineId"), thread.get("threadId")
            if not isinstance(line_id, str) or not isinstance(thread_id, str):
                raise TransitError("invalid_response")
            schedule = thread.get("BriefSchedule", {})
            if not isinstance(schedule, dict) or not isinstance(
                schedule.get("Events", []), list
            ):
                raise TransitError("invalid_response")
            arrivals = []
            for event in schedule.get("Events", []):
                if not isinstance(event, dict):
                    raise TransitError("invalid_response")
                for field, source in (
                    ("Estimated", "estimated"),
                    ("Scheduled", "scheduled"),
                ):
                    departure = event.get(field)
                    timestamp = (
                        _timestamp(departure.get("value"))
                        if isinstance(departure, dict)
                        else None
                    )
                    if timestamp is not None:
                        if timestamp > max(now, server_time):
                            arrivals.append(Arrival(timestamp, source))
                        # A past valid forecast means this event has passed;
                        # do not resurrect it using its later scheduled time.
                        break
            stops = thread.get("EssentialStops", [])
            if not isinstance(stops, list):
                raise TransitError("invalid_response")
            termini = [
                stop["name"]
                for stop in stops
                if isinstance(stop, dict)
                and isinstance(stop.get("name"), str)
                and isinstance(stop.get("info"), dict)
                and stop["info"].get("lastStop")
            ]
            directions.append(
                Direction(
                    line_id,
                    thread_id,
                    str(transport.get("name", "")),
                    ", ".join(termini) or thread_id,
                    tuple(sorted(arrivals, key=lambda item: item.timestamp)),
                )
            )
    return StopSnapshot(stop_id, data["name"], now, server_time, tuple(directions))
