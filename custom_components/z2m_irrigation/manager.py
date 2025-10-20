from __future__ import annotations

import json
from typing import Callable, Dict, Set

from homeassistant.core import HomeAssistant
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIG_NEW_VALVE

class ValveManager:
    """Discovers Sonoff SWV valves from Zigbee2MQTT and announces them."""

    def __init__(self, hass: HomeAssistant, base_topic: str, manual_names: list[str] | None = None):
        self.hass = hass
        self.base_topic = base_topic.strip().strip("/")
        self.manual_names = manual_names or []
        self._known: Set[str] = set()
        self._unsubs: list[Callable[[], None]] = []

    async def start(self) -> None:
        # Subscribe to bridge/devices to learn existing devices
        topic = f"{self.base_topic}/bridge/devices"
        self._unsubs.append(await mqtt.async_subscribe(self.hass, topic, self._on_devices))
        # Ask Z2M to (re)publish devices
        await mqtt.async_publish(self.hass, f"{self.base_topic}/bridge/devices/get", "", qos=0, retain=False)

        # Also emit any manual names the user typed
        for name in self.manual_names:
            self._announce(name)

    async def stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    async def _on_devices(self, msg) -> None:
        try:
            devices = json.loads(msg.payload)
        except Exception:
            return
        for dev in devices or []:
            # Prefer robust checks: Sonoff SWV model
            model = (dev.get("definition") or {}).get("model")
            vendor = (dev.get("definition") or {}).get("vendor")
            name = dev.get("friendly_name")
            if not name:
                continue
            if model == "SWV" or (vendor == "SONOFF" and "valve" in (dev.get("description","")+dev.get("type","")).lower()):
                self._announce(name)

    def _announce(self, name: str) -> None:
        if name in self._known:
            return
        self._known.add(name)
        async_dispatcher_send(self.hass, SIG_NEW_VALVE, name, self.base_topic)
