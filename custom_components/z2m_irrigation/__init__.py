from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, CONF_MANUAL_TOPICS, PLATFORMS,
)
from .manager import ValveManager

SERVICE_START_TIMED = "start_timed"
SERVICE_START_LITERS = "start_liters"
SERVICE_RESET_TOTALS = "reset_totals"
SERVICE_RESCAN = "rescan"

SCHEMA_START_TIMED = vol.Schema({vol.Required("valve"): cv.string, vol.Required("minutes"): vol.Coerce(float)})
SCHEMA_START_LITERS = vol.Schema({vol.Required("valve"): cv.string, vol.Required("liters"): vol.Coerce(float)})
SCHEMA_RESET_TOTALS = vol.Schema({vol.Optional("valve"): cv.string})

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    base = entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    manual = [s.strip() for s in (entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines() if s.strip()]
    mgr = ValveManager(hass, base, manual)
    hass.data[DOMAIN][entry.entry_id] = mgr

    async def _start_timed(call):
        mgr.start_timed(call.data["valve"], call.data["minutes"])

    async def _start_liters(call):
        mgr.start_liters(call.data["valve"], call.data["liters"])

    async def _reset_totals(call):
        mgr.reset_totals(call.data.get("valve"))

    async def _rescan(call):
        await mgr.async_stop()
        await mgr.async_start()

    hass.services.async_register(DOMAIN, SERVICE_START_TIMED, _start_timed, SCHEMA_START_TIMED)
    hass.services.async_register(DOMAIN, SERVICE_START_LITERS, _start_liters, SCHEMA_START_LITERS)
    hass.services.async_register(DOMAIN, SERVICE_RESET_TOTALS, _reset_totals, SCHEMA_RESET_TOTALS)
    hass.services.async_register(DOMAIN, SERVICE_RESCAN, _rescan)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await mgr.async_start()

    async def _options_updated(hass: HomeAssistant, changed_entry: ConfigEntry) -> None:
        if changed_entry.entry_id != entry.entry_id:
            return
        await mgr.async_stop()
        base2 = changed_entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        manual2 = [s.strip() for s in (changed_entry.options.get(CONF_MANUAL_TOPICS, "") or "").splitlines() if s.strip()]
        mgr.base = base2
        mgr.manual_topics = manual2
        await mgr.async_start()

    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    await mgr.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
