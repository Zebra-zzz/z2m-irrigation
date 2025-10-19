from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS, OPT_MANUAL_VALVES, OPT_BASE_TOPIC
from .manager import ValveManager

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    base = entry.options.get(OPT_BASE_TOPIC, "zigbee2mqtt")
    manuals = entry.options.get(OPT_MANUAL_VALVES, [])
    mgr = ValveManager(hass, base, manuals)
    hass.data[DOMAIN][entry.entry_id] = mgr
    await mgr.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    async def _svc_timed(call):
        await mgr.turn_on_for(call.data["base"], int(call.data["minutes"]))
    async def _svc_litres(call):
        await mgr.turn_on_for_litres(call.data["base"], float(call.data["litres"]), int(call.data.get("failsafe_minutes",180)))
    hass.services.async_register(DOMAIN, "start_timed_run", _svc_timed)
    hass.services.async_register(DOMAIN, "start_litres_run", _svc_litres)
    return True

async def _options_updated(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok: hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
