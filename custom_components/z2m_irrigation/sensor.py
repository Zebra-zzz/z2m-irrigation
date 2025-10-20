from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .manager import ValveManager, Valve
from .const import DOMAIN, MANUFACTURER, MODEL, SIG_NEW_VALVE, sig_update

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]

    def _add_for(v: Valve):
        async_add_entities(
            [
                FlowLpmSensor(mgr, v),
                SessionUsedSensor(mgr, v),
                TotalLitersSensor(mgr, v),
                TotalMinutesSensor(mgr, v),
            ]
        )

    for v in list(mgr.valves.values()):
        _add_for(v)

    async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_for)

class BaseValveSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, mgr: ValveManager, valve: Valve, name_suffix: str) -> None:
        self.mgr = mgr
        self.valve = valve
        self._attr_name = name_suffix
        self._sig = sig_update(valve.topic)
        self._unsub = None

    @property
    def unique_id(self) -> str:
        return f"{self.valve.topic}_{self.name}".lower().replace(" ", "_")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.valve.topic)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self.valve.name,
        )

    async def async_added_to_hass(self) -> None:
        def _cb():
            self.async_write_ha_state()
        self._unsub = async_dispatcher_connect(self.hass, self._sig, _cb)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub(); self._unsub = None

class FlowLpmSensor(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Flow")
        self._attr_native_unit_of_measurement = "L/min"
        self._attr_state_class = "measurement"

    @property
    def native_value(self):
        return round(self.valve.flow_lpm, 2)

class SessionUsedSensor(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Session Used")
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = "measurement"

    @property
    def native_value(self):
        return round(self.valve.session_liters, 2)

class TotalLitersSensor(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Total")
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = "total_increasing"

    @property
    def native_value(self):
        return round(self.valve.total_liters, 2)

class TotalMinutesSensor(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Total Minutes")
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = "total_increasing"

    @property
    def native_value(self):
        return round(self.valve.total_minutes, 1)
