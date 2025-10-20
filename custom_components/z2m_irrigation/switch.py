from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIG_NEW_VALVE, SIG_UPDATE_VALVE

def _dev_info(name: str):
    return {
        "identifiers": {(DOMAIN, name)},
        "manufacturer": "Sonoff",
        "model": "SWV",
        "name": name,
    }

class ValveSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Valve"

    def __init__(self, name: str):
        self._name = name

    @property
    def unique_id(self): return f"{self._name}_switch"
    @property
    def device_info(self): return _dev_info(self._name)
    @property
    def is_on(self):
        v = self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].valves.get(self._name)
        return False if not v else v.running

    async def async_turn_on(self, **kwargs):
        await self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].turn_on(self._name)
    async def async_turn_off(self, **kwargs):
        await self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].turn_off(self._name)

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIG_UPDATE_VALVE, self._maybe_update))

    @callback
    def _maybe_update(self, name: str):
        if name == self._name: self.async_write_ha_state()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    hass.data[DOMAIN+"_entry"] = entry.entry_id
    mgr = hass.data[DOMAIN][entry.entry_id]

    ents = [ValveSwitch(n) for n in mgr.valves.keys()]
    async_add_entities(ents)

    @callback
    def _add(name: str):
        async_add_entities([ValveSwitch(name)])
    hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, _add)
