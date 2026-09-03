"""Configure stop IDs and explicit route directions using standard HA flows."""

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_INTERVAL, DOMAIN, MAX_INTERVAL
from .models import Direction, StopSnapshot, TransitError, stop_id_from_url
from .runtime import borrow


def settings_schema(routes: str = "", interval: int = DEFAULT_INTERVAL) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("routes", default=routes): str,
            vol.Required("scan_interval", default=interval): vol.All(
                int, vol.Range(min=60, max=MAX_INTERVAL)
            ),
        }
    )


def candidates(snapshot: StopSnapshot, routes: str) -> list[Direction]:
    requested = {r.strip() for r in re.split(r"[,;\n]", routes) if r.strip()}
    found = [d for d in snapshot.directions if d.route in requested]
    if not requested or {d.route for d in found} != requested:
        raise TransitError("route_not_found")
    return found


def direction_schema(directions: list[Direction]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("directions"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    multiple=True,
                    options=[
                        selector.SelectOptionDict(
                            value=d.key,
                            label=f"№ {d.route} → {d.name} ({d.line_id}, {d.thread_id})",
                        )
                        for d in directions
                    ],
                )
            )
        }
    )


def chosen(directions: list[Direction], values: list[str]) -> list[dict[str, str]]:
    selected = [d for d in directions if d.key in values]
    if (
        not values
        or len(set(values)) != len(values)
        or {d.key for d in selected} != set(values)
        or {d.route for d in selected} != {d.route for d in directions}
    ):
        raise TransitError("select_direction")
    return [d.selection() for d in selected]


def error_key(error: TransitError) -> str:
    code = str(error)
    return (
        code
        if code
        in {"invalid_url", "invalid_interval", "route_not_found", "select_direction"}
        else "cannot_connect"
    )


def validate_interval(value) -> int:
    if type(value) is not int or not 60 <= value <= MAX_INTERVAL:
        raise TransitError("invalid_interval")
    return value


class TransitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TransitOptionsFlow()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                interval = validate_interval(user_input["scan_interval"])
                stop_id = stop_id_from_url(user_input["stop_url"])
                await self.async_set_unique_id(stop_id)
                self._abort_if_unique_id_configured()
                async with borrow(self.hass) as client:
                    snapshot = await client.async_stop(stop_id, interval)
                self._directions = candidates(snapshot, user_input["routes"])
                self._data = {
                    "stop_id": stop_id,
                    "stop_name": snapshot.name,
                    "scan_interval": interval,
                }
                if len({d.route for d in self._directions}) != len(self._directions):
                    return await self.async_step_select()
                return self._finish([d.selection() for d in self._directions])
            except TransitError as error:
                errors["base"] = error_key(error)
        schema = settings_schema().extend({vol.Required("stop_url"): str})
        return self.async_show_form(step_id="user", errors=errors, data_schema=schema)

    async def async_step_select(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                return self._finish(chosen(self._directions, user_input["directions"]))
            except TransitError as error:
                errors["base"] = error_key(error)
        return self.async_show_form(
            step_id="select",
            errors=errors,
            description_placeholders={"stop_name": self._data["stop_name"]},
            data_schema=direction_schema(self._directions),
        )

    def _finish(self, selections) -> ConfigFlowResult:
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._data["stop_name"], data={**self._data, "selections": selections}
        )


class TransitOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        entry = self.config_entry
        current = entry.options or entry.data
        errors = {}
        if user_input is not None:
            try:
                self._interval = validate_interval(user_input["scan_interval"])
                coordinator = getattr(entry, "runtime_data", None)
                snapshot = coordinator.data if coordinator is not None else None
                if snapshot is None:
                    async with borrow(self.hass) as client:
                        snapshot = await client.async_stop(
                            entry.data["stop_id"], self._interval
                        )
                self._directions = candidates(snapshot, user_input["routes"])
                if len({d.route for d in self._directions}) != len(self._directions):
                    return await self.async_step_select()
                return self._finish([d.selection() for d in self._directions])
            except TransitError as error:
                errors["base"] = error_key(error)
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=settings_schema(
                ", ".join(dict.fromkeys(s["route"] for s in current["selections"])),
                current["scan_interval"],
            ),
        )

    async def async_step_select(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                return self._finish(chosen(self._directions, user_input["directions"]))
            except TransitError as error:
                errors["base"] = error_key(error)
        return self.async_show_form(
            step_id="select",
            errors=errors,
            description_placeholders={"stop_name": self.config_entry.data["stop_name"]},
            data_schema=direction_schema(self._directions),
        )

    def _finish(self, selections) -> ConfigFlowResult:
        return self.async_create_entry(
            title="", data={"scan_interval": self._interval, "selections": selections}
        )
