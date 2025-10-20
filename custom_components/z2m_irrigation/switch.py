from __future__ import annotations

import json
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async def _add(name: str, base_topic: str):
        async_add_entities([Z2MValveSwitch(hass, name, base_topic)], True)
    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    entry.async_on_unload(unsub)

class Z2MValveSwitch(SwitchEntity):
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, name: str, base_topic: str):
        self.hass = hass
        self._name = name
        self._base = base_topic.strip().strip("/")
        self._state = False
        self._unsub = None

    @property
    def unique_id(self) -> str:
        return f"{self._name}_switch"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> bool:
        return self._state

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
            st = data.get("state")
            if isinstance(st, str):
                self._state = (st.upper() == "ON")
                self.async_write_ha_state()
        self._unsub = await mqtt.async_subscribe(self.hass, topic, _msg)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await mqtt.async_publish(self.hass, f"{self._base}/{self._name}/set", json.dumps({"state":"ON"}), qos=0, retain=False)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await mqtt.async_publish(self.hass, f"{self._base}/{self._name}/set", json.dumps({"state":"OFF"}), qos=0, retain=False)
        self._state = False
        self.async_write_ha_state()
