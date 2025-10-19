from __future__ import annotations
import json, hashlib
from typing import Callable, Optional
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.switch import SwitchEntity
from homeassistant.components import mqtt
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN, OPT_VALVES

def _name_from_topic(base: str) -> str:
    # last segment as name, fall back to hash
    seg = base.strip("/").split("/")[-1]
    return seg or ("Valve " + hashlib.md5(base.encode()).hexdigest()[:6])

class MQTTValveSwitch(SwitchEntity):
    _attr_should_poll = False
    _unsub: Optional[Callable] = None

    def __init__(self, hass: HomeAssistant, base_topic: str):
        self.hass = hass
        self._base = base_topic.strip("/")
        self._attr_name = _name_from_topic(self._base)
        self._attr_unique_id = f"{DOMAIN}:{hashlib.md5(self._base.encode()).hexdigest()}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"dev:{self._base}")},
            manufacturer="Sonoff",
            model="Zigbee Water Valve",
            name=self._attr_name,
        )
        self._attr_is_on = False

    async def async_added_to_hass(self):
        @callback
        def _msg(msg):
            try:
                data = json.loads(msg.payload)
                state = str(data.get("state") or data.get("valve") or "").upper()
                if state in ("ON", "OPEN", "1", "TRUE"):
                    self._attr_is_on = True
                elif state in ("OFF", "CLOSE", "CLOSED", "0", "FALSE"):
                    self._attr_is_on = False
                self.async_write_ha_state()
            except Exception:
                # Ignore non-JSON messages
                pass
        self._unsub = await mqtt.async_subscribe(self.hass, self._base, _msg)

    async def async_will_remove_from_hass(self):
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def async_turn_on(self, **kwargs):
        await mqtt.async_publish(self.hass, f"{self._base}/set", json.dumps({"state":"ON"}), qos=0, retain=False)

    async def async_turn_off(self, **kwargs):
        await mqtt.async_publish(self.hass, f"{self._base}/set", json.dumps({"state":"OFF"}), qos=0, retain=False)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    cfg = hass.data[DOMAIN][entry.entry_id]
    bases = cfg.get(OPT_VALVES, [])
    entities = [MQTTValveSwitch(hass, base) for base in bases]
    if entities:
        async_add_entities(entities)
