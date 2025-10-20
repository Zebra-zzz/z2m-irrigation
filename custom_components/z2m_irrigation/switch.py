from __future__ import annotations
import json
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components import mqtt
from .const import DOMAIN
from .manager import ValveManager, SIG_NEW_VALVE, sig_update

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]

    @callback
    def _add(topic: str):
        async_add_entities([ValveSwitch(mgr, topic)], True)

    # add known valves
    for topic in list(mgr.valves.keys()):
        _add(topic)

    # discover new valves
    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    entry.async_on_unload(unsub)

class ValveSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, mgr: ValveManager, topic: str):
        self.mgr = mgr
        self._topic = topic
        self._data = mgr.valves.get(topic, {})
        self._unsub = None
        self._attr_name = "Valve"
        self._attr_unique_id = f"{mgr.base}/{topic}#switch"

    @property
    def is_on(self) -> bool | None:
        v = self._data.get("state")
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().upper() in ("ON", "OPEN", "1", "TRUE")
        return None

    @property
    def extra_state_attributes(self):
        return {k: v for k, v in self._data.items() if k != "state"}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.mgr.base}/{self._topic}")},
            name=self._topic,
            manufacturer="Sonoff",
            model="SWV",
        )

    async def async_turn_on(self, **kwargs):
        await mqtt.async_publish(
            self.hass, f"{self.mgr.base}/{self._topic}/set", json.dumps({"state": "ON"})
        )

    async def async_turn_off(self, **kwargs):
        await mqtt.async_publish(
            self.hass, f"{self.mgr.base}/{self._topic}/set", json.dumps({"state": "OFF"})
        )

    @callback
    def _handle_update(self):
        self._data = self.mgr.valves.get(self._topic, {})
        # Only write state once entity is attached to a platform
        if getattr(self, "entity_id", None) and getattr(self, "platform", None):
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        # Subscribe only after entity is added (prevents early state writes)
        self._unsub = async_dispatcher_connect(self.hass, sig_update(self._topic), self._handle_update)
        self._handle_update()  # push initial state if available

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
