from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_BASE_TOPIC,
    DEFAULT_BASE_TOPIC,
    CONF_MANUAL_TOPICS,
    SIG_NEW_VALVE,
    Z2M_MODEL,
    sig_update,
)
from .history import SessionHistory

_LOGGER = logging.getLogger(__name__)

@dataclass
class Valve:
    topic: str
    name: str
    state: str = "OFF"
    flow_lpm: float = 0.0
    last_ts: float = field(default_factory=time.monotonic)
    session_active: bool = False
    session_start_ts: float = 0.0
    session_liters: float = 0.0
    session_end_ts: Optional[float] = None  # for timed runs; remaining time sensor
    total_liters: float = 0.0
    total_minutes: float = 0.0
    target_liters: Optional[float] = None
    cancel_handle: Optional[Callable[[], None]] = None
    session_count: int = 0
    battery: Optional[int] = None
    link_quality: Optional[int] = None
    current_session_id: Optional[str] = None  # Track current Supabase session ID
    trigger_type: str = "manual"  # Track how valve was triggered

class ValveManager:
    def __init__(
        self,
        hass: HomeAssistant,
        base_topic: str = DEFAULT_BASE_TOPIC,
        manual_topics: Iterable[str] = (),
        flow_scale: float = 1.0,
    ) -> None:
        self.hass = hass
        self.base = base_topic or DEFAULT_BASE_TOPIC
        self.manual_topics = [t for t in (manual_topics or []) if t]
        self.flow_scale = float(flow_scale or 1.0)
        self.valves: Dict[str, Valve] = {}
        self._unsubs: list[Callable[[], None]] = []
        self.history = SessionHistory(hass)

    async def async_start(self) -> None:
        _LOGGER.debug("Starting ValveManager base=%s manual=%s scale=%s", self.base, self.manual_topics, self.flow_scale)
        # Subscriptions for device list (two possible topics)
        self._unsubs.append(
            await mqtt.async_subscribe(self.hass, f"{self.base}/bridge/devices", self._on_devices)
        )
        self._unsubs.append(
            await mqtt.async_subscribe(self.hass, f"{self.base}/bridge/config/devices", self._on_devices)
        )
        # Subscribe to all manual topics immediately
        for topic in self.manual_topics:
            self._ensure_valve(topic, topic)

        # Ask Z2M to send the device list
        await mqtt.async_publish(self.hass, f"{self.base}/bridge/config/devices/get", "")
        _LOGGER.debug("Requested device list on %s/bridge/config/devices/get", self.base)

    async def async_stop(self) -> None:
        _LOGGER.debug("Stopping ValveManager")
        while self._unsubs:
            self._unsubs.pop()()

    # ---------- internal helpers ----------
    def _dispatch_signal(self, signal: str, *args) -> None:
        """Always fire dispatcher on HA loop thread (safe from any callback thread)."""
        self.hass.add_job(async_dispatcher_send, self.hass, signal, *args)

    @callback
    def _on_devices(self, msg) -> None:
        try:
            devices = json.loads(msg.payload)
        except Exception as e:
            _LOGGER.debug("Device list parse error: %s", e)
            return
        if not isinstance(devices, list):
            return

        added = 0
        for d in devices:
            model = (d.get("definition") or {}).get("model") or d.get("model")
            if model != Z2M_MODEL:
                continue
            topic = d.get("friendly_name") or d.get("friendlyName")
            if not topic or topic in self.valves:
                continue
            self._ensure_valve(topic, topic)
            added += 1
        if added:
            _LOGGER.info("Discovered %d Sonoff SWV valve(s)", added)

    def _ensure_valve(self, topic: str, name: str) -> None:
        if topic in self.valves:
            return
        v = Valve(topic=topic, name=name)
        self.valves[topic] = v

        async def _sub():
            self._unsubs.append(
                await mqtt.async_subscribe(
                    self.hass, f"{self.base}/{topic}", lambda m: self._on_state(topic, m)
                )
            )
            _LOGGER.debug("Subscribed to %s/%s", self.base, topic)
        self.hass.async_create_task(_sub())

        # announce new valve safely
        self._dispatch_signal(SIG_NEW_VALVE, v)

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

        # integrate flow -> liters & minutes
        if v.session_active:
            liters = (v.flow_lpm / 60.0) * dt
            if liters > 0:
                v.session_liters += liters
                v.total_liters += liters
                v.total_minutes += dt / 60.0

                # Check if volume target reached
                if v.target_liters and v.session_liters >= v.target_liters:
                    _LOGGER.info(
                        "Volume target reached for %s: %.2f/%.2f L - turning off",
                        topic, v.session_liters, v.target_liters
                    )
                    self.hass.async_create_task(self.async_turn_off(topic))

        # state transitions
        if "state" in data:
            new_state = str(data.get("state")).upper()
            if new_state in ("ON", "OPEN", "1", "TRUE"):
                new_state = "ON"
                if not v.session_active:
                    v.session_active = True
                    v.session_start_ts = now
                    v.session_liters = 0.0
                    v.session_count += 1
                    # Log session start to Supabase
                    target = v.target_liters if v.target_liters else (v.session_end_ts - now) / 60.0 if v.session_end_ts else None
                    self.hass.async_create_task(
                        self._log_session_start(v, target)
                    )
            else:
                new_state = "OFF"
                if v.session_active:
                    session_duration = (now - v.session_start_ts) / 60.0
                    avg_flow = v.session_liters / session_duration if session_duration > 0 else 0
                    # Log session end to Supabase
                    if v.current_session_id:
                        self.hass.async_create_task(
                            self.history.end_session(
                                v.current_session_id,
                                session_duration,
                                v.session_liters,
                                avg_flow
                            )
                        )
                        v.current_session_id = None
                    v.session_active = False
                    v.target_liters = None
                    v.session_end_ts = None
                    v.trigger_type = "manual"
                    if v.cancel_handle:
                        v.cancel_handle(); v.cancel_handle = None
            v.state = new_state

        # flow normalization to L/min
        # Sonoff SWV reports flow in m³/h, convert to L/min
        if "flow_lpm" in data:
            try:
                v.flow_lpm = float(data["flow_lpm"]) or 0.0
            except Exception:
                v.flow_lpm = 0.0
        elif "flow" in data:
            try:
                raw_flow = float(data["flow"]) or 0.0
                # Device reports in m³/h
                # Convert m³/h to L/min: multiply by 1000/60 = 16.667
                # Then apply user's flow_scale if needed (default 1.0)
                v.flow_lpm = raw_flow * 16.667 * self.flow_scale
            except Exception:
                v.flow_lpm = 0.0

        # optional absolute total from device (convert m³ to L if needed)
        if "consumption" in data:
            try:
                dev_total = float(data["consumption"])
                # If consumption is in m³, convert to liters
                if dev_total < 100:  # Likely m³
                    dev_total = dev_total * 1000
                if dev_total >= 0 and dev_total > v.total_liters:
                    v.total_liters = dev_total
            except Exception:
                pass

        # battery and link quality
        if "battery" in data:
            try:
                v.battery = int(data["battery"])
            except Exception:
                pass
        if "linkquality" in data or "link_quality" in data:
            try:
                v.link_quality = int(data.get("linkquality") or data.get("link_quality"))
            except Exception:
                pass

        # liters target reached?
        if v.session_active and v.target_liters is not None and v.session_liters >= v.target_liters:
            self.hass.async_create_task(self.async_turn_off(v.topic))
            v.target_liters = None
            v.session_end_ts = None

        # SAFE dispatcher fire
        self._dispatch_signal(sig_update(topic))

    async def _log_session_start(self, v: Valve, target_value: Optional[float] = None) -> None:
        """Helper to log session start to Supabase"""
        session_id = await self.history.start_session(
            v.topic,
            v.name,
            v.trigger_type,
            target_value
        )
        v.current_session_id = session_id

    async def async_turn_on(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "ON"}), qos=1)

    async def async_turn_off(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "OFF"}), qos=1)

    def reset_totals(self, topic: str | None = None) -> None:
        if topic is None:
            for v in self.valves.values():
                v.total_liters = 0.0
                v.total_minutes = 0.0
                v.session_liters = 0.0
                v.session_count = 0
        else:
            v = self.valves.get(topic)
            if v:
                v.total_liters = 0.0
                v.total_minutes = 0.0
                v.session_liters = 0.0
                v.session_count = 0
        # safe wildcard notify
        self._dispatch_signal(sig_update(topic or "*"))

    def start_liters(self, topic: str, liters: float) -> None:
        """Start valve for specified liters with HA-based monitoring"""
        v = self.valves.get(topic)
        if not v:
            return
        v.target_liters = max(0.0, float(liters))
        v.session_end_ts = None
        v.trigger_type = "volume"

        _LOGGER.info("Starting volume run: %s for %.2f L (HA monitoring)", topic, liters)

        # Sonoff SWV does not support water_consumed parameter via Z2M
        # Use simple ON and HA will monitor flow and turn off when target reached
        self.hass.async_create_task(self.async_turn_on(topic))

    def start_timed(self, topic: str, minutes: float) -> None:
        """Start valve for specified minutes with HA-based timer"""
        v = self.valves.get(topic)
        if not v:
            return
        if v.cancel_handle:
            v.cancel_handle(); v.cancel_handle = None

        now = time.monotonic()
        run_s = max(0.0, float(minutes)) * 60.0
        v.session_end_ts = now + run_s
        v.trigger_type = "timed"

        _LOGGER.info("Starting timed run: %s for %.2f min (HA timer)", topic, minutes)

        # Sonoff SWV does not support timer parameter via Z2M
        # Use simple ON and HA timer will turn off when duration reached
        self.hass.async_create_task(self.async_turn_on(topic))

        # Set HA-side timer to turn off
        async def _off(_):
            _LOGGER.info("Timer expired for %s - turning off", topic)
            await self.async_turn_off(topic)
            if v.cancel_handle:
                v.cancel_handle(); v.cancel_handle = None
            v.session_end_ts = None

        v.cancel_handle = async_call_later(self.hass, run_s, _off)
