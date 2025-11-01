from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .manager import ValveManager, Valve
from .const import DOMAIN, MANUFACTURER, MODEL, SIG_NEW_VALVE, sig_update

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]["manager"]

    @callback
    def _add_numbers(valve: Valve):
        async_add_entities([
            TargetMinutesNumber(mgr, valve),
            TargetLitersNumber(mgr, valve),
        ], True)

    for valve in list(mgr.valves.values()):
        _add_numbers(valve)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_numbers)
    )

class BaseNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, mgr: ValveManager, valve: Valve, name: str) -> None:
        self.mgr = mgr
        self.valve = valve
        self._attr_name = name
        self._sig = sig_update(valve.topic)
        self._unsub = None
        self._value = 0.0

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

    @property
    def native_value(self) -> float:
        return self._value

    async def async_added_to_hass(self) -> None:
        @callback
        def _update():
            self.async_write_ha_state()
        self._unsub = async_dispatcher_connect(self.hass, self._sig, _update)
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

class TargetMinutesNumber(BaseNumber):
    _attr_native_min_value = 1
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer"

    def __init__(self, mgr: ValveManager, valve: Valve) -> None:
        super().__init__(mgr, valve, "Run for Minutes")
        self._value = 10.0

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.async_write_ha_state()
        self.mgr.start_timed(self.valve.topic, value)

class TargetLitersNumber(BaseNumber):
    _attr_native_min_value = 1
    _attr_native_max_value = 1000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "L"
    _attr_icon = "mdi:water"

    def __init__(self, mgr: ValveManager, valve: Valve) -> None:
        super().__init__(mgr, valve, "Run for Liters")
        self._value = 50.0

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.async_write_ha_state()
        self.mgr.start_liters(self.valve.topic, value)
