from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BASE_TOPIC,
    DEFAULT_BASE_TOPIC,
    SIG_NEW_VALVE,
    Z2M_MODEL,
    sig_update,
)

@dataclass
class Valve:
    topic: str                # zigbee2mqtt friendly_name (MQTT leaf topic)
    name: str                 # device name to show
    state: str = "OFF"        # ON/OFF
    flow_lpm: float = 0.0     # current flow in L/min from Z2M
    last_ts: float = field(default_factory=time.monotonic)
    # per-session
    session_active: bool = False
    session_start_ts: float = 0.0
    session_liters: float = 0.0
    # totals
    total_liters: float = 0.0
    total_minutes: float = 0.0
    # liters-based target
    target_liters: Optional[float] = None
    # timer handle for timed runs
    cancel_handle: Optional[Callable[[], None]] = None


class ValveManager:
    def __init__(self, hass: HomeAssistant, base_topic: str = DEFAULT_BASE_TOPIC) -> None:
        self.hass = hass
        self.base = base_topic or DEFAULT_BASE_TOPIC
        self.valves: Dict[str, Valve] = {}      # key=topic
        self._unsubs: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        # devices list (for discovery)
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base}/bridge/devices", self._on_devices
            )
        )
        # Many setups already publish retained state on "<base>/<friendly_name>"
        # We'll subscribe lazily when a valve is known (see _watch_valve)

        # Request device list (Z2M will answer retained anyway)
        await mqtt.async_publish(self.hass, f"{self.base}/bridge/config/devices/get", "")

    async def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    # ---- discovery ----
    @callback
    def _on_devices(self, msg) -> None:
        try:
            devices = json.loads(msg.payload)
        except Exception:
            return
        for d in devices:
            if d.get("definition", {}).get("model") != Z2M_MODEL:
                continue
            topic = d.get("friendly_name")
            if not topic or topic in self.valves:
                continue
            self._add_valve(topic, topic)

    def _add_valve(self, topic: str, name: str) -> None:
        v = Valve(topic=topic, name=name)
        self.valves[topic] = v

        # Listen to this device's state messages
        async def _sub():
            self._unsubs.append(
                await mqtt.async_subscribe(
                    self.hass, f"{self.base}/{topic}", lambda m: self._on_state(topic, m)
                )
            )
        self.hass.async_create_task(_sub())

        async_dispatcher_send(self.hass, SIG_NEW_VALVE, v)

    # ---- state processing ----
    @callback
    def _on_state(self, topic: str, msg) -> None:
        v = self.valves.get(topic)
        if not v:
            return
        try:
            data = json.loads(msg.payload)
        except Exception:
            return

        now = time.monotonic()
        dt = max(0.0, now - v.last_ts)
        v.last_ts = now

        # integrate flow (liters) while ON using last known flow value
        if v.session_active:
            # liters added during dt seconds (flow is L/min)
            liters = (v.flow_lpm / 60.0) * dt
            v.session_liters += liters
            v.total_liters += liters
            v.total_minutes += dt / 60.0

        # live values from payload
        if "state" in data:
            new_state = data.get("state")
            if new_state == "ON" and not v.session_active:
                v.session_active = True
                v.session_start_ts = now
                v.session_liters = 0.0
            elif new_state == "OFF" and v.session_active:
                v.session_active = False
                v.target_liters = None
                if v.cancel_handle:
                    v.cancel_handle(); v.cancel_handle = None
            v.state = new_state

        if "flow" in data:
            try:
                v.flow_lpm = float(data["flow"]) or 0.0
            except Exception:
                v.flow_lpm = 0.0

        # liters target reached?
        if v.session_active and v.target_liters is not None and v.session_liters >= v.target_liters:
            self.hass.async_create_task(self.async_turn_off(v.topic))
            v.target_liters = None

        async_dispatcher_send(self.hass, sig_update(topic))

    # ---- actions (MQTT commands) ----
    async def async_turn_on(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "ON"}), qos=1, retain=False)

    async def async_turn_off(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "OFF"}), qos=1, retain=False)

    # user features
    def reset_totals(self, topic: str | None = None) -> None:
        if topic is None:
            for v in self.valves.values():
                v.total_liters = 0.0
                v.total_minutes = 0.0
        else:
            v = self.valves.get(topic)
            if v:
                v.total_liters = 0.0
                v.total_minutes = 0.0
                v.session_liters = 0.0
        async_dispatcher_send(self.hass, sig_update(topic or "*"))

    def start_liters(self, topic: str, liters: float) -> None:
        v = self.valves.get(topic)
        if not v:
            return
        v.target_liters = max(0.0, float(liters))
        self.hass.async_create_task(self.async_turn_on(topic))

    def start_timed(self, topic: str, minutes: float) -> None:
        from homeassistant.helpers.event import async_call_later

        v = self.valves.get(topic)
        if not v:
            return
        # cancel previous
        if v.cancel_handle:
            v.cancel_handle()
            v.cancel_handle = None

        def _cancel() -> None:
            if v.cancel_handle:
                v.cancel_handle()
                v.cancel_handle = None

        async def _turn_off(_now) -> None:
            await self.async_turn_off(topic)
            _cancel()

        v.cancel_handle = async_call_later(self.hass, float(minutes) * 60.0, _turn_off)
        self.hass.async_create_task(self.async_turn_on(topic))
