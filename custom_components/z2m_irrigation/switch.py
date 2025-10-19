from __future__ import annotations
import hashlib
from typing import Optional, Callable
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, SIG_NEW_VALVE
from .manager import ValveManager

class ValveSwitch(SwitchEntity):
    _attr_should_poll = False
    def __init__(self, mgr: ValveManager, base: str):
        self.mgr = mgr
        self.base = base
        v = mgr.valves[base]
        self._attr_name = v.name
        self._attr_unique_id = f"{DOMAIN}:switch:{v.uid}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"dev:{base}")},
                                            manufacturer="Sonoff", model="Zigbee Water Valve", name=v.name)

    @property
    def is_on(self) -> bool:
        return self.mgr.valves[self.base].is_on

    async def async_turn_on(self, **kwargs):
        await self.mgr.turn_on_for(self.base, 120)  # default 2h if clicked directly

    async def async_turn_off(self, **kwargs):
        await self.hass.services.async_call(DOMAIN, "start_timed_run", {"base": self.base, "minutes": 0}, blocking=False)

    @callback
    def _state_changed(self):
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        self.async_on_remove(self.hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, self._maybe_update))
    @callback
    def _maybe_update(self, base: str):
        if base == self.base:
            self._state_changed()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    def _add_if_needed(base: str):
        if any(getattr(e, "base", None) == base for e in getattr(async_add_entities, "_added_entities", [])):
            return
        async_add_entities([ValveSwitch(mgr, base)])
    for base in list(mgr.valves.keys()):
        _add_if_needed(base)
    hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, _add_if_needed)
