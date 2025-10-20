from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from .const import DOMAIN
from .manager import ValveManager

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if entry.entry_id in hass.data[DOMAIN]:
        _LOGGER.debug("Entry %s already set up; skipping.", entry.entry_id)
        return True

    mgr = ValveManager(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = mgr

    # Ensure platforms are ready before discovery/subscriptions start
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start manager (MQTT subscriptions / discovery)
    await mgr.async_start()
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mgr: ValveManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if mgr:
        await mgr.async_stop()
    return ok
