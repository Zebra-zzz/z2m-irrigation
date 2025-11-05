from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from datetime import timedelta

from .const import (
    CONF_BASE_TOPIC,
    DEFAULT_BASE_TOPIC,
    CONF_MANUAL_TOPICS,
    SIG_NEW_VALVE,
    Z2M_MODEL,
    sig_update,
)
from .database import IrrigationDatabase

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
    total_liters: float = 0.0  # Resettable total
    total_minutes: float = 0.0  # Resettable total
    lifetime_total_liters: float = 0.0  # NEVER resets
    lifetime_total_minutes: float = 0.0  # NEVER resets
    lifetime_session_count: int = 0  # NEVER resets
    last_24h_liters: float = 0.0  # Last 24 hours
    last_24h_minutes: float = 0.0  # Last 24 hours
    last_7d_liters: float = 0.0  # Last 7 days
    last_7d_minutes: float = 0.0  # Last 7 days
    target_liters: Optional[float] = None
    cancel_handle: Optional[Callable[[], None]] = None
    session_count: int = 0  # Resettable count
    battery: Optional[int] = None
    link_quality: Optional[int] = None
    current_session_id: Optional[str] = None  # Track current session ID
    trigger_type: str = "manual"  # Track how valve was triggered
    last_session_start: Optional[str] = None  # ISO datetime of last session start

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
        self.db = IrrigationDatabase(hass)

    def _schedule_task(self, coro):
        """Schedule an async task from a callback (thread-safe)."""
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(coro)
        )

    async def async_start(self) -> None:
        _LOGGER.debug("Starting ValveManager base=%s manual=%s scale=%s", self.base, self.manual_topics, self.flow_scale)

        # Initialize local database
        await self.db.async_init()

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

        # Start periodic refresh of 24h/7d sensors every 15 minutes
        self._unsubs.append(
            async_track_time_interval(
                self.hass,
                self._periodic_refresh_time_metrics,
                timedelta(minutes=15)
            )
        )
        _LOGGER.debug("Started periodic 24h/7d sensor refresh (every 15 minutes)")

        # Ask Z2M to send the device list (ignore if MQTT not ready)
        try:
            await mqtt.async_publish(self.hass, f"{self.base}/bridge/config/devices/get", "")
            _LOGGER.debug("Requested device list on %s/bridge/config/devices/get", self.base)
        except Exception as e:
            _LOGGER.warning("Could not request device list (MQTT not ready?): %s - will discover valves from MQTT messages", e)

    async def async_stop(self) -> None:
        _LOGGER.debug("Stopping ValveManager")
        while self._unsubs:
            self._unsubs.pop()()

    async def _periodic_refresh_time_metrics(self, now=None) -> None:
        """Periodically refresh 24h/7d sensors and last session start (every 15 minutes)"""
        _LOGGER.debug("🔄 Periodic refresh: Updating 24h/7d sensors for all valves")

        for topic, v in self.valves.items():
            try:
                # Refresh 24h metrics
                last_24h = await self.db.get_usage_last_24h(topic)
                v.last_24h_liters, v.last_24h_minutes = last_24h

                # Refresh 7d metrics
                last_7d = await self.db.get_usage_last_7d(topic)
                v.last_7d_liters, v.last_7d_minutes = last_7d

                # Refresh last session start
                v.last_session_start = await self.db.get_last_session_start(topic)

                _LOGGER.debug("✅ Refreshed %s: 24h=%.2fL, 7d=%.2fL, last session: %s",
                             v.name, v.last_24h_liters, v.last_7d_liters, v.last_session_start)

                # Notify sensors to update
                self._dispatch_signal(sig_update(topic))

            except Exception as e:
                _LOGGER.error("❌ Error refreshing time metrics for %s: %s", topic, e, exc_info=True)

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

            # Load persisted totals from local database
            totals = await self.db.load_valve_totals(topic)
            v.lifetime_total_liters = totals["lifetime_total_liters"]
            v.lifetime_total_minutes = totals["lifetime_total_minutes"]
            v.lifetime_session_count = totals["lifetime_session_count"]
            v.total_liters = totals["resettable_total_liters"]
            v.total_minutes = totals["resettable_total_minutes"]
            v.session_count = totals["resettable_session_count"]

            # Load time-based metrics
            _LOGGER.debug(f"Loading time-based metrics for topic={repr(topic)} (type={type(topic)})")
            last_24h = await self.db.get_usage_last_24h(topic)
            v.last_24h_liters, v.last_24h_minutes = last_24h

            last_7d = await self.db.get_usage_last_7d(topic)
            v.last_7d_liters, v.last_7d_minutes = last_7d

            # Load last session start datetime
            v.last_session_start = await self.db.get_last_session_start(topic)

            _LOGGER.info("Loaded totals for %s: %.2f L lifetime, %.2f L resettable, %.2f L (24h), %.2f L (7d), last session: %s",
                        name, v.lifetime_total_liters, v.total_liters, v.last_24h_liters, v.last_7d_liters, v.last_session_start)

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

        # FAILSAFE: Check targets even when valve is ON (not just during session_active)
        # This ensures we catch cases where device fails to stop
        if v.state == "ON":
            # FAILSAFE: Check if volume target reached (backup to native device control)
            if v.target_liters and v.target_liters > 0:
                if v.session_liters >= v.target_liters:
                    _LOGGER.warning(
                        "FAILSAFE: Volume target reached for %s: %.2f/%.2f L - forcing OFF",
                        topic, v.session_liters, v.target_liters
                    )
                    self._schedule_task(self.async_turn_off(topic))
                    v.target_liters = None  # Clear target to prevent repeated triggers
                    return
                else:
                    # Debug log to see progress
                    _LOGGER.debug(
                        "Volume run progress for %s: %.2f/%.2f L (%.1f%%), flow: %.2f L/min",
                        topic, v.session_liters, v.target_liters,
                        (v.session_liters / v.target_liters * 100), v.flow_lpm
                    )

            # FAILSAFE: Check if time target reached (backup to native device control)
            if v.session_end_ts and v.session_start_ts > 0:
                if now >= v.session_end_ts:
                    elapsed_min = (now - v.session_start_ts) / 60.0
                    target_min = (v.session_end_ts - v.session_start_ts) / 60.0
                    _LOGGER.warning(
                        "FAILSAFE: Time target reached for %s: %.2f/%.2f min - forcing OFF",
                        topic, elapsed_min, target_min
                    )
                    self._schedule_task(self.async_turn_off(topic))
                    v.session_end_ts = None  # Clear target to prevent repeated triggers
                    return

        # state transitions
        if "state" in data:
            new_state = str(data.get("state")).upper()
            if new_state in ("ON", "OPEN", "1", "TRUE"):
                new_state = "ON"
                if not v.session_active:
                    _LOGGER.debug(f"🚿 [MANAGER] Session starting for {v.name}")
                    v.session_active = True
                    v.session_start_ts = now
                    v.session_liters = 0.0
                    v.session_count += 1
                    # Generate session ID immediately before valve can turn off
                    from datetime import datetime
                    v.current_session_id = f"{v.topic}_{datetime.now().timestamp()}"
                    _LOGGER.debug(f"🚿 [MANAGER] Generated session_id: {v.current_session_id}")
                    # Log session start to local database
                    target = v.target_liters if v.target_liters else (v.session_end_ts - now) / 60.0 if v.session_end_ts else None
                    _LOGGER.debug(f"🚿 [MANAGER] Logging session start for {v.name}, target={target}")
                    self._schedule_task(
                        self._log_session_start(v, target, v.current_session_id)
                    )
            else:
                new_state = "OFF"
                if v.session_active:
                    session_duration = (now - v.session_start_ts) / 60.0
                    avg_flow = v.session_liters / session_duration if session_duration > 0 else 0
                    _LOGGER.debug(f"🛑 [MANAGER] Session ending for {v.name}: {session_duration:.2f}min, {v.session_liters:.2f}L, {avg_flow:.2f}lpm")
                    # Log session end to local database and update totals
                    if v.current_session_id:
                        # CRITICAL: Capture session_id NOW before clearing it
                        # This prevents race condition where session_id becomes None
                        captured_session_id = v.current_session_id
                        captured_session_liters = v.session_liters
                        captured_topic = v.topic
                        captured_name = v.name

                        async def _end_and_sync():
                            # End session in database using captured values
                            await self.db.end_session(
                                captured_session_id,
                                session_duration,
                                captured_session_liters,
                                avg_flow
                            )
                            # Update totals in database
                            updated_totals = await self.db.save_valve_totals(
                                captured_topic,
                                captured_name,
                                captured_session_liters,
                                session_duration
                            )
                            # Sync totals back to valve object
                            if updated_totals:
                                v.lifetime_total_liters = updated_totals["lifetime_total_liters"]
                                v.lifetime_total_minutes = updated_totals["lifetime_total_minutes"]
                                v.lifetime_session_count = updated_totals["lifetime_session_count"]
                                v.total_liters = updated_totals["resettable_total_liters"]
                                v.total_minutes = updated_totals["resettable_total_minutes"]
                                v.session_count = updated_totals["resettable_session_count"]

                            # Update time-based metrics
                            _LOGGER.debug(f"🔄 Updating time-based metrics for {captured_name}")
                            _LOGGER.debug(f"   v.topic={repr(captured_topic)} (type={type(captured_topic)})")

                            last_24h = await self.db.get_usage_last_24h(captured_topic)
                            v.last_24h_liters, v.last_24h_minutes = last_24h
                            _LOGGER.debug(f"   24h: {v.last_24h_liters:.2f}L, {v.last_24h_minutes:.2f}min")

                            last_7d = await self.db.get_usage_last_7d(captured_topic)
                            v.last_7d_liters, v.last_7d_minutes = last_7d
                            _LOGGER.debug(f"   7d: {v.last_7d_liters:.2f}L, {v.last_7d_minutes:.2f}min")

                            # Update last session start datetime
                            v.last_session_start = await self.db.get_last_session_start(captured_topic)
                            _LOGGER.debug(f"   last session start: {v.last_session_start}")

                            self._dispatch_signal(sig_update(captured_topic))
                        self._schedule_task(_end_and_sync())
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

        # Failsafe volume check is handled earlier in this method

        # SAFE dispatcher fire
        self._dispatch_signal(sig_update(topic))

    async def _log_session_start(self, v: Valve, target_value: Optional[float] = None, session_id: str = None) -> None:
        """Helper to log session start to local database"""
        # Session ID should already be set on the valve object
        if not session_id:
            _LOGGER.error(f"❌ No session_id provided for {v.name} - this should not happen!")
            return

        # Determine target liters or minutes
        target_liters = v.target_liters if v.target_liters else None
        target_minutes = target_value if not v.target_liters and target_value else None

        await self.db.start_session(
            session_id,
            v.topic,
            v.name,
            v.trigger_type,
            target_liters,
            target_minutes
        )

    async def async_turn_on(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "ON"}), qos=1)

    async def async_turn_off(self, topic: str) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps({"state": "OFF"}), qos=1)

    def reset_totals(self, topic: str | None = None) -> None:
        """Reset ONLY resettable totals (lifetime totals are preserved)"""
        async def _reset_in_database(v_topic: str):
            # Reset in local database first
            success = await self.db.reset_resettable_totals(v_topic)
            if success:
                # Then sync to in-memory valve object
                v = self.valves.get(v_topic)
                if v:
                    v.total_liters = 0.0
                    v.total_minutes = 0.0
                    v.session_liters = 0.0
                    v.session_count = 0
                    self._dispatch_signal(sig_update(v_topic))
                    _LOGGER.info("Reset resettable totals for %s (lifetime preserved: %.2f L)",
                                v.name, v.lifetime_total_liters)

        if topic is None:
            # Reset all valves
            for v in self.valves.values():
                self._schedule_task(_reset_in_database(v.topic))
        else:
            # Reset specific valve
            if topic in self.valves:
                self._schedule_task(_reset_in_database(topic))

    def start_liters(self, topic: str, liters: float) -> None:
        """Start valve for specified liters - HA monitoring only (device clears native commands)"""
        v = self.valves.get(topic)
        if not v:
            return
        v.target_liters = max(0.0, float(liters))
        v.session_end_ts = None
        v.trigger_type = "volume"

        _LOGGER.info("Starting volume run: %s for %.2f L (HA monitoring)", topic, liters)

        # NOTE: Sonoff SWV clears cyclic_quantitative_irrigation immediately after starting
        # Z2M logs show: device accepts command, starts valve, then clears irrigation_capacity to 0
        # Therefore we use simple ON/OFF and HA monitors flow to turn off at target
        self.hass.async_create_task(self.async_turn_on(topic))

    def start_timed(self, topic: str, minutes: float) -> None:
        """Start valve for specified minutes using native cyclic_timed_irrigation"""
        v = self.valves.get(topic)
        if not v:
            return
        if v.cancel_handle:
            v.cancel_handle(); v.cancel_handle = None

        now = time.monotonic()
        run_s = max(0.0, float(minutes)) * 60.0
        v.session_end_ts = now + run_s
        v.trigger_type = "timed"

        _LOGGER.info("Starting timed run: %s for %.2f min (native device control + HA backup)", topic, minutes)

        # Use Sonoff SWV's native cyclic_timed_irrigation feature
        # Set total_number=1 for single run, irrigation_interval=0 for immediate start
        seconds = int(min(run_s, 86400))  # Max 86400 seconds per device spec
        payload = {
            "cyclic_timed_irrigation": {
                "current_count": 0,
                "total_number": 1,
                "irrigation_duration": seconds,
                "irrigation_interval": 0
            }
        }
        self.hass.async_create_task(
            mqtt.async_publish(self.hass, f"{self.base}/{topic}/set", json.dumps(payload), qos=1)
        )

        # FAILSAFE: Set HA-side backup timer in case device doesn't respond
        # This timer will fire if device fails to turn off at target time
        async def _off(_):
            _LOGGER.warning("FAILSAFE: Backup timer expired for %s - forcing OFF", topic)
            await self.async_turn_off(topic)
            if v.cancel_handle:
                v.cancel_handle(); v.cancel_handle = None
            v.session_end_ts = None

        v.cancel_handle = async_call_later(self.hass, run_s, _off)
