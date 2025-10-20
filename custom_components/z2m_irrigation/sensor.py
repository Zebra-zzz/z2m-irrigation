from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import UnitOfVolume, UnitOfTime
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIG_NEW_VALVE, SIG_UPDATE_VALVE

def _dev_info(name: str):
    return {
        "identifiers": {(DOMAIN, name)},
        "manufacturer": "Sonoff",
        "model": "SWV",
        "name": name,
    }

class _BaseValveSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, name: str): self._name = name
    @property
    def unique_id(self): return f"{self._name}_sensor_{self.__class__.__name__}"
    @property
    def device_info(self): return _dev_info(self._name)
    @property
    def name(self): return self.__class__.__name__.replace("_"," ")

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIG_UPDATE_VALVE, self._maybe_update))

    @callback
    def _maybe_update(self, name: str):
        if name == self._name: self.async_write_ha_state()

class FlowLpmSensor(_BaseValveSensor):
    _attr_native_unit_of_measurement = "L/min"
    def __init__(self, name): super().__init__(name)
    @property
    def state_class(self): return SensorStateClass.MEASUREMENT
    @property
    def native_value(self):
        mgr = self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].valves.get(self._name)
        return None if not mgr else round(mgr.last_lpm, 2)

class SessionUsedSensor(_BaseValveSensor):
    _attr_translation_key = "session_used"
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    @property
    def state_class(self): return SensorStateClass.MEASUREMENT
    @property
    def device_class(self): return None
    @property
    def native_value(self):
        v = self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].valves.get(self._name)
        return None if not v else round(max(0.0, v.session_liters), 2)

class TotalLitersSensor(_BaseValveSensor):
    _attr_translation_key = "total"
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    @property
    def device_class(self): return SensorDeviceClass.WATER
    @property
    def state_class(self): return SensorStateClass.TOTAL_INCREASING
    @property
    def native_value(self):
        v = self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].valves.get(self._name)
        return None if not v else round(max(0.0, v.total_liters), 2)

class TotalMinutesSensor(_BaseValveSensor):
    _attr_translation_key = "total_time"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    @property
    def device_class(self): return SensorDeviceClass.DURATION
    @property
    def state_class(self): return SensorStateClass.TOTAL_INCREASING
    @property
    def native_value(self):
        v = self.hass.data[DOMAIN][self.hass.data[DOMAIN+"_entry"]].valves.get(self._name)
        return None if not v else round(max(0.0, v.total_minutes), 1)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    # Save entry id for sensor access to manager
    hass.data[DOMAIN+"_entry"] = entry.entry_id
    mgr = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for name in mgr.valves.keys():
        entities += [FlowLpmSensor(name), SessionUsedSensor(name), TotalLitersSensor(name), TotalMinutesSensor(name)]
    async_add_entities(entities)

    @callback
    def _add(name: str):
        async_add_entities([FlowLpmSensor(name), SessionUsedSensor(name), TotalLitersSensor(name), TotalMinutesSensor(name)])
    hass.helpers.dispatcher.async_dispatcher_connect(SIG_NEW_VALVE, _add)
