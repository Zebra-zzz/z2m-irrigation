from __future__ import annotations
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN
from .manager import ValveManager, SIG_NEW_VALVE, sig_update

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]

    @callback
    def _add(topic: str):
        async_add_entities([FlowSensor(mgr, topic)], True)

    for topic in list(mgr.valves.keys()):
        _add(topic)

    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    entry.async_on_unload(unsub)

class FlowSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, mgr: ValveManager, topic: str):
        self.mgr = mgr
        self._topic = topic
        self._data = mgr.valves.get(topic, {})
        self._unsub = None
        self._attr_name = "Flow"
        self._attr_unique_id = f"{mgr.base}/{topic}#flow"
        self._attr_native_unit_of_measurement = self._guess_unit()

    def _guess_unit(self):
        if "flow_lpm" in self._data or "flow" in self._data:
            return "L/min"
        if "consumption" in self._data:
            return "L"
        return None

    @property
    def native_value(self):
        for key in ("flow_lpm", "flow", "consumption"):
            if key in self._data:
                return self._data.get(key)
        return None

    @property
    def extra_state_attributes(self):
        return dict(self._data)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.mgr.base}/{self._topic}")},
            name=self._topic,
            manufacturer="Sonoff",
            model="SWV",
        )

    @callback
    def _handle_update(self):
        self._data = self.mgr.valves.get(self._topic, {})
        if not self._attr_native_unit_of_measurement:
            self._attr_native_unit_of_measurement = self._guess_unit()
        if getattr(self, "entity_id", None) and getattr(self, "platform", None):
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(self.hass, sig_update(self._topic), self._handle_update)
        self._handle_update()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
