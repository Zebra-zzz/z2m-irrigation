from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN, PLATFORMS, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, CONF_MANUAL_VALVES
from .manager import ValveManager

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    base = entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    manual = entry.options.get(CONF_MANUAL_VALVES, [])
    if isinstance(manual, str):
        manual = [l.strip() for l in manual.splitlines() if l.strip()]

    manager = ValveManager(hass, base_topic=base, manual_names=manual)
    await manager.start()
    hass.data[DOMAIN][entry.entry_id] = {"manager": manager}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True

async def _async_reload_on_options(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})
    manager: ValveManager | None = data.get("manager")
    if manager:
        await manager.stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return ok
