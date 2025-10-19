from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr = hass.data[DOMAIN][entry.entry_id]["manager"]
    ents = [Z2MValveSwitch(mgr, b) for b in mgr.valves.keys()]
    async_add_entities(ents)

    def _maybe_add(base: str):
        if base not in [e.base for e in ents]:
            e = Z2MValveSwitch(mgr, base)
            ents.append(e)
            async_add_entities([e])

    entry.async_on_unload(async_dispatcher_connect(hass, SIG_NEW_VALVE, _maybe_add))

class Z2MValveSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, manager, base: str):
        self.manager = manager
        self.base = base

    @property
    def name(self):
        return self.state_obj.name if hasattr(self, "state_obj") else self.manager.valves[self.base].name

    @property
    def unique_id(self):
        return f"{self.manager.valves[self.base].uid}_switch"

    @property
    def is_on(self):
        return self.manager.valves[self.base].is_on

    async def async_turn_on(self, **kwargs):
        await self.manager.turn_on_for(self.base, 0)

    async def async_turn_off(self, **kwargs):
        await self.manager.turn_off(self.base)

    async def async_added_to_hass(self):
        self.state_obj = self.manager.valves[self.base]
        self.async_on_remove(async_dispatcher_connect(self.hass, SIG_NEW_VALVE, self._maybe_update))

    async def _maybe_update(self, base: str):
        if base == self.base:
            self.schedule_update_ha_state()
