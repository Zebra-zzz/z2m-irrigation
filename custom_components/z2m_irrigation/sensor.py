from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, SIG_NEW_VALVE
from .manager import ValveManager

class _Base(SensorEntity):
    _attr_should_poll = False
    def __init__(self, mgr: ValveManager, base: str, name: str, uid: str):
        self.mgr = mgr; self.base = base
        self._attr_name = name
        self._attr_unique_id = uid
        v = mgr.valves[base]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"dev:{base}")},
                                            manufacturer="Sonoff", model="Zigbee Water Valve", name=v.name)

    async def async_added_to_hass(self):
        self.async_on_remove(self.hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, self._maybe_update))

    @callback
    def _maybe_update(self, base: str):
        if base == self.base:
            self.async_write_ha_state()

class FlowLMin(_Base):
    def __init__(self, mgr, base):
        v = mgr.valves[base]
        super().__init__(mgr, base, f"{v.name} Flow", f"{DOMAIN}:flow:{v.uid}")
        self._attr_native_unit_of_measurement = "L/min"

    @property
    def native_value(self):
        return round(self.mgr.valves[self.base].flow_l_min, 2)

class TotalLitres(_Base):
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    def __init__(self, mgr, base):
        v = mgr.valves[base]
        super().__init__(mgr, base, f"{v.name} Total", f"{DOMAIN}:total:{v.uid}")
        self._attr_native_unit_of_measurement = "L"

    @property
    def native_value(self):
        return round(self.mgr.valves[self.base].total_l, 2)

class SessionUsed(_Base):
    def __init__(self, mgr, base):
        v = mgr.valves[base]
        super().__init__(mgr, base, f"{v.name} Session Used", f"{DOMAIN}:session:{v.uid}")
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = None  # not a long-term statistic

    @property
    def native_value(self):
        return round(self.mgr.valves[self.base].session_used_l, 2)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    def _add(base: str):
        v = mgr.valves[base]
        async_add_entities([FlowLMin(mgr, base), TotalLitres(mgr, base), SessionUsed(mgr, base)])
    for base in list(mgr.valves.keys()):
        _add(base)
    hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, _add)
