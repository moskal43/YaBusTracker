"""YaBusTracker custom integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .coordinator import TransitCoordinator
from .models import entity_unique_id
from .runtime import acquire, release

type TransitConfigEntry = ConfigEntry[TransitCoordinator]
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: TransitConfigEntry) -> bool:
    runtime = acquire(hass)
    coordinator = None
    try:
        coordinator = TransitCoordinator(hass, entry, runtime)
        # Load unavailable source states even on initial failure so the shared
        # cooldown survives HA setup and recovery remains automatic.
        await coordinator.async_refresh()
        entry.runtime_data = coordinator
        selections = entry.options.get("selections", entry.data["selections"])
        keep = {
            entity_unique_id(entry.data["stop_id"], selected) for selected in selections
        }
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.unique_id not in keep:
                registry.async_remove(entity.entity_id)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        if coordinator is not None:
            await coordinator.async_shutdown()
        await release(hass, runtime)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TransitConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        await release(hass, entry.runtime_data.runtime)
        return True
    return False
