from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .manager import ValveManager, Valve
from .const import DOMAIN, MANUFACTURER, MODEL, SIG_NEW_VALVE, sig_update

async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    def _add_for(v: Valve):
        async_add_entities([
            FlowLpm(mgr, v),
            SessionUsed(mgr, v),
            TotalLiters(mgr, v),
            TotalMinutes(mgr, v),
            SessionRemaining(mgr, v),
        ], True)
    for v in list(mgr.valves.values()):
        _add_for(v)
    entry.async_on_unload(async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_for))

class BaseValveSensor(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, mgr: ValveManager, valve: Valve, name: str, unit: str | None, state_class: str | None):
        self.mgr = mgr; self.valve = valve
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._sig = sig_update(valve.topic); self._unsub = None
    @property
    def unique_id(self) -> str:
        base = f"{self.valve.topic}_{self.name}".lower().replace(" ", "_")
        return base
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.valve.topic)}, manufacturer=MANUFACTURER, model=MODEL, name=self.valve.name)
    async def async_added_to_hass(self) -> None:
        def _cb(): self.async_write_ha_state()
        self._unsub = async_dispatcher_connect(self.hass, self._sig, _cb)
        # push an initial state so the entity shows immediately
        self.async_write_ha_state()
    async def async_will_remove_from_hass(self) -> None:
        if self._unsub: self._unsub(); self._unsub = None

class FlowLpm(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Flow", "L/min", "measurement")
    @property
    def native_value(self): return round(self.valve.flow_lpm, 3)

class SessionUsed(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Session Used", "L", "measurement")
    @property
    def native_value(self): return round(self.valve.session_liters, 2)

class TotalLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Total", "L", "total_increasing")
    @property
    def native_value(self): return round(self.valve.total_liters, 2)

class TotalMinutes(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Total Minutes", "min", "total_increasing")
    @property
    def native_value(self): return round(self.valve.total_minutes, 2)

class SessionRemaining(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Session Remaining", "min", "measurement")
    @property
    def native_value(self):
        # Only meaningful when a timed run is scheduled
        if self.valve.session_end_ts is None:
            return None
        remaining_s = max(0.0, self.valve.session_end_ts - self.valve.last_ts)
        return round(remaining_s / 60.0, 2)
