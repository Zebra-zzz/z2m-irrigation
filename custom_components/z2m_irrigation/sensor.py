from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr = hass.data[DOMAIN][entry.entry_id]["manager"]
    def build(base):
        v = mgr.valves[base]
        return [
            FlowSensor(mgr, base),
            TotalSensor(mgr, base),
            SessionUsedSensor(mgr, base),
        ]
    entities = []
    for b in list(mgr.valves.keys()):
        entities.extend(build(b))
    async_add_entities(entities)

    def _add_if_new(base: str):
        if base not in [e.base for e in entities if hasattr(e, "base")]:
            async_add_entities(build(base))

    entry.async_on_unload(async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_if_new))

class _Base(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, manager, base: str):
        self.mgr = manager
        self.base = base
        self.v = manager.valves[base]
    @property
    def device_info(self):
        v = self.v
        return {
            "identifiers": {(DOMAIN, f"{v.uid}_{v.name}")},
            "manufacturer": "Sonoff",
            "model": "Zigbee Water Valve",
            "name": v.name,
        }
    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIG_NEW_VALVE, self._maybe_update))
    async def _maybe_update(self, base: str):
        if base == self.base:
            self.v = self.mgr.valves[base]
            self.schedule_update_ha_state()

class FlowSensor(_Base):
    @property
    def name(self): return f"{self.v.name} Flow"
    @property
    def unique_id(self): return f"{self.v.uid}_flow"
    @property
    def native_unit_of_measurement(self): return UnitOfVolumeFlowRate.LITERS_PER_MINUTE
    @property
    def device_class(self): return SensorDeviceClass.VOLUME_FLOW_RATE
    @property
    def state_class(self): return SensorStateClass.MEASUREMENT
    @property
    def native_value(self): return round(self.v.flow_l_min, 2)

class TotalSensor(_Base):
    @property
    def name(self): return f"{self.v.name} Total"
    @property
    def unique_id(self): return f"{self.v.uid}_total"
    @property
    def native_unit_of_measurement(self): return UnitOfVolume.LITERS
    @property
    def device_class(self): return SensorDeviceClass.WATER
    @property
    def state_class(self): return SensorStateClass.TOTAL_INCREASING
    @property
    def native_value(self): return round(self.v.total_l, 2)

class SessionUsedSensor(_Base):
    @property
    def name(self): return f"{self.v.name} Session Used"
    @property
    def unique_id(self): return f"{self.v.uid}_session_used"
    @property
    def native_unit_of_measurement(self): return UnitOfVolume.LITERS
    @property
    def state_class(self): return SensorStateClass.MEASUREMENT
    @property
    def native_value(self): return round(self.v.session_used_l, 2)
