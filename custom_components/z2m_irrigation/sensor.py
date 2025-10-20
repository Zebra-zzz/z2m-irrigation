from __future__ import annotations

import json
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    def _add(name: str, base_topic: str):
        async_add_entities([
            FlowSensor(hass, name, base_topic),
            SessionUsedSensor(hass, name, base_topic),
            TotalUsedSensor(hass, name, base_topic),
        ], True)
    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    entry.async_on_unload(unsub)

class _BaseValveSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, name: str, base_topic: str):
        self.hass = hass
        self._name = name
        self._base = base_topic.strip().strip("/")
        self._unsub = None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._name)},
            "manufacturer": "Sonoff",
            "model": "SWV",
            "name": self._name,
        }

    async def async_added_to_hass(self) -> None:
        topic = f"{self._base}/{self._name}"
        async def _msg(msg):
            try:
                data = json.loads(msg.payload)
            except Exception:
                return
            await self._process(data)
        self._unsub = await mqtt.async_subscribe(self.hass, topic, _msg)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _process(self, data: dict[str, Any]) -> None:
        return

class FlowSensor(_BaseValveSensor):
    @property
    def unique_id(self) -> str:
        return f"{self._name}_flow"

    @property
    def name(self) -> str:
        return "Flow"

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolumeFlowRate.LITERS_PER_MINUTE

    @property
    def device_class(self):
        return SensorDeviceClass.VOLUME_FLOW_RATE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    async def _process(self, data: dict[str, Any]) -> None:
        flow = data.get("flow")
        if isinstance(flow, (int, float)):
            self._attr_native_value = float(flow)
            self.async_write_ha_state()

class SessionUsedSensor(_BaseValveSensor):
    """Accumulates liters during a session; resets when valve turns OFF."""

    def __init__(self, hass, name, base_topic):
        super().__init__(hass, name, base_topic)
        self._last_ts = None
        self._last_flow = 0.0
        self._liters = 0.0
        self._is_on = False

    @property
    def unique_id(self) -> str:
        return f"{self._name}_session_used"

    @property
    def name(self) -> str:
        return "Session Used"

    @property
    def device_class(self):
        return SensorDeviceClass.WATER

    @property
    def state_class(self):
        return SensorStateClass.TOTAL

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.LITERS

    async def _process(self, data: dict[str, Any]) -> None:
        st = data.get("state")
        if isinstance(st, str):
            is_on = (st.upper() == "ON")
            if self._is_on and not is_on:
                # valve turned OFF -> finalize session and reset counter
                self._last_ts = None
                self._last_flow = 0.0
                self._liters = 0.0
                self._attr_native_value = 0.0
                self._is_on = False
                self.async_write_ha_state()
            else:
                self._is_on = is_on

        flow = data.get("flow")
        now = time.time()
        if isinstance(flow, (int, float)) and self._is_on:
            if self._last_ts is not None:
                dt = max(0.0, now - self._last_ts)      # seconds
                # liters += (L/min) * (sec/60)
                self._liters += float(flow) * (dt/60.0)
                self._attr_native_value = round(self._liters, 2)
                self.async_write_ha_state()
            self._last_ts = now
            self._last_flow = float(flow)
        elif isinstance(flow, (int, float)):
            # update timestamp even if off to avoid spikes when turning on
            self._last_ts = now
            self._last_flow = float(flow)

class TotalUsedSensor(_BaseValveSensor):
    """Accumulates liters across runtime (resets on HA restart)."""

    def __init__(self, hass, name, base_topic):
        super().__init__(hass, name, base_topic)
        self._last_ts = None
        self._last_flow = 0.0
        self._liters = 0.0

    @property
    def unique_id(self) -> str:
        return f"{self._name}_total"

    @property
    def name(self) -> str:
        return "Total"

    @property
    def device_class(self):
        return SensorDeviceClass.WATER

    @property
    def state_class(self):
        return SensorStateClass.TOTAL_INCREASING

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.LITERS

    async def _process(self, data: dict[str, Any]) -> None:
        flow = data.get("flow")
        now = time.time()
        if isinstance(flow, (int, float)):
            if self._last_ts is not None:
                dt = max(0.0, now - self._last_ts)
                self._liters += float(flow) * (dt/60.0)
                self._attr_native_value = round(self._liters, 2)
                self.async_write_ha_state()
            self._last_ts = now
            self._last_flow = float(flow)
