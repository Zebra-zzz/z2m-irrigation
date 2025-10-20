from __future__ import annotations
import json, logging
from typing import Callable, Dict, Any, List
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage

_LOGGER = logging.getLogger(__name__)

DOMAIN = "z2m_irrigation"
SIG_NEW_VALVE = "z2m_irrigation_new_valve"
def sig_update(topic: str) -> str: return f"z2m_irrigation_update_{topic}"

class ValveManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        opts = entry.options or {}
        self.base: str = (opts.get("base") or "zigbee2mqtt").strip() or "zigbee2mqtt"
        manual: str = (opts.get("manual") or "").strip()
        self.manual_topics: List[str] = [t.strip() for t in manual.splitlines() if t.strip()]
        self.valves: Dict[str, Dict[str, Any]] = {}
        self._unsubs: List[Callable[[], None]] = []

    async def async_start(self) -> None:
        _LOGGER.info("Z2M Irrigation starting (base=%s, manual=%s)", self.base, self.manual_topics)
        self._unsubs.append(await mqtt.async_subscribe(self.hass, f"{self.base}/bridge/state", self._on_bridge_state))
        self._unsubs.append(await mqtt.async_subscribe(self.hass, f"{self.base}/bridge/devices", self._on_devices))
        for topic in self.manual_topics:
            self._unsubs.append(await mqtt.async_subscribe(self.hass, f"{self.base}/{topic}", self._mk_state_cb(topic)))
        await self._request_devices_safe()

    async def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    async def _request_devices_safe(self) -> None:
        try:
            await mqtt.async_publish(self.hass, f"{self.base}/bridge/config/devices/get", "")
            _LOGGER.debug("Requested device list on %s/bridge/config/devices/get", self.base)
        except Exception as e:
            _LOGGER.debug("MQTT not ready (%s); retry in 2s", e)
            async_call_later(self.hass, 2, lambda *_: self.hass.async_create_task(self._request_devices_safe()))

    @callback
    async def _on_bridge_state(self, msg: ReceiveMessage) -> None:
        if (msg.payload or "").strip().lower() == "online":
            await self._request_devices_safe()

    @callback
    async def _on_devices(self, msg: ReceiveMessage) -> None:
        try:
            devices = json.loads(msg.payload)
        except Exception as e:
            _LOGGER.warning("Bad /bridge/devices payload: %s", e)
            return
        discovered = []
        for d in devices if isinstance(devices, list) else []:
            model = ((d.get("definition") or {}).get("model") or "").upper()
            if model == "SWV":
                friendly = d.get("friendly_name")
                if friendly:
                    discovered.append(friendly)
                    await self._ensure_valve(friendly)
        if discovered:
            _LOGGER.info("Discovered %d Sonoff SWV valve(s): %s", len(discovered), ", ".join(discovered))

    def _mk_state_cb(self, topic: str):
        @callback
        async def _cb(msg: ReceiveMessage) -> None:
            await self._on_state(topic, msg)
        return _cb

    @callback
    async def _on_state(self, topic: str, msg: ReceiveMessage) -> None:
        try:
            data = json.loads(msg.payload) if msg.payload else {}
        except Exception as e:
            _LOGGER.debug("Non-JSON state for %s: %s (payload=%r)", topic, e, msg.payload)
            return
        self.valves.setdefault(topic, {}).update(data)
        async_dispatcher_send(self.hass, sig_update(topic))

    async def _ensure_valve(self, topic: str) -> None:
        if topic not in self.valves:
            self.valves[topic] = {}
            async_dispatcher_send(self.hass, SIG_NEW_VALVE, topic)
        sub = await mqtt.async_subscribe(self.hass, f"{self.base}/{topic}", self._mk_state_cb(topic))
        self._unsubs.append(sub)
