from __future__ import annotations
import json
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components import mqtt
from .const import DOMAIN
from .manager import ValveManager, sig_update, SIG_NEW_VALVE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    entities: list[ValveSwitch] = []

    def _add(topic: str):
        ent = ValveSwitch(hass, entry.entry_id, mgr, topic)
        entities.append(ent)
        async_add_entities([ent])

    unsub = async_dispatcher_connect(hass, SIG_NEW_VALVE, _add)
    mgr._unsubs.append(unsub)  # unregister with manager on stop

    for t in list(mgr.valves.keys()):
        _add(t)

class ValveSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Valve"

    def __init__(self, hass: HomeAssistant, entry_id: str, mgr: ValveManager, topic: str) -> None:
        self.hass = hass
        self._mgr = mgr
        self._topic = topic
        self._attr_unique_id = f"{entry_id}_{topic}_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{topic}")},
            manufacturer="Sonoff",
            model="SWV",
            name=topic,
            via_device=(DOMAIN, entry_id),
        )
        self._state = False
        self._unsub = async_dispatcher_connect(hass, sig_update(topic), self._maybe_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub(); self._unsub = None  # type: ignore

    @callback
    def _maybe_update(self) -> None:
        data = self._mgr.valves.get(self._topic, {})
        self._state = (str(data.get("state", "")).upper() == "ON")
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        await mqtt.async_publish(self.hass, f"{self._mgr.base}/{self._topic}/set", json.dumps({"state": "ON"}))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await mqtt.async_publish(self.hass, f"{self._mgr.base}/{self._topic}/set", json.dumps({"state": "OFF"}))
