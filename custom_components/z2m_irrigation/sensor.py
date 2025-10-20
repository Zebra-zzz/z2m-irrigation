from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN
from .manager import ValveManager, sig_update, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    entities: list[FlowSensor] = []

    def _add(topic: str):
        ent = FlowSensor(hass, entry.entry_id, mgr, topic)
        entities.append(ent)
        async_add_entities([ent])

    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    mgr._unsubs.append(unsub)  # unregister on stop

    for t in list(mgr.valves.keys()):
        _add(t)

class FlowSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Flow"
    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE

    def __init__(self, hass: HomeAssistant, entry_id: str, mgr: ValveManager, topic: str) -> None:
        self.hass = hass
        self._mgr = mgr
        self._topic = topic
        self._attr_unique_id = f"{entry_id}_{topic}_flow"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{topic}")},
            manufacturer="Sonoff",
            model="SWV",
            name=topic,
            via_device=(DOMAIN, entry_id),
        )
        self._val = 0.0
        self._unsub = async_dispatcher_connect(hass, sig_update(topic), self._maybe_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub(); self._unsub = None  # type: ignore

    @callback
    def _maybe_update(self) -> None:
        data = self._mgr.valves.get(self._topic, {})
        try:
            self._val = float(data.get("flow", 0.0))
        except Exception:
            self._val = 0.0
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self._val
