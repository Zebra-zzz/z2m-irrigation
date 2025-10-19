from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, DEFAULT_BASE_TOPIC, CONF_BASE_TOPIC, CONF_MANUAL_BASES
from .manager import ValveManager

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    base = entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    manual = entry.options.get(CONF_MANUAL_BASES, [])
    mgr = ValveManager(hass, base_topic=base, manual_bases=manual)
    hass.data[DOMAIN][entry.entry_id] = {"manager": mgr}
    await mgr.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
