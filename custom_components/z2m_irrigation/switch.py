from __future__ import annotations
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .manager import ValveManager, Valve
from .const import DOMAIN, MANUFACTURER, MODEL, SIG_NEW_VALVE, sig_update

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    def _add(v: Valve): async_add_entities([ValveSwitch(mgr, v)])
    for v in list(mgr.valves.values()): _add(v)
    async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)

class ValveSwitch(SwitchEntity):
    _attr_has_entity_name = True; _attr_name = "Valve"
    def __init__(self, mgr: ValveManager, valve: Valve): self.mgr=mgr; self.valve=valve; self._sig=sig_update(valve.topic); self._unsub=None
    @property
    def unique_id(self) -> str: return f"{self.valve.topic}_switch".lower().replace(" ", "_")
    @property
    def is_on(self) -> bool: return self.valve.state == "ON"
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.valve.topic)}, manufacturer=MANUFACTURER, model=MODEL, name=self.valve.name)
    async def async_added_to_hass(self) -> None:
        def _cb(): self.async_write_ha_state()
        self._unsub = async_dispatcher_connect(self.hass, self._sig, _cb)
    async def async_will_remove_from_hass(self) -> None:
        if self._unsub: self._unsub(); self._unsub=None
    async def async_turn_on(self, **kwargs) -> None: await self.mgr.async_turn_on(self.valve.topic)
    async def async_turn_off(self, **kwargs) -> None: await self.mgr.async_turn_off(self.valve.topic)
