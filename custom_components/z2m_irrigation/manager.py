from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Iterable

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, callback
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
    # v3.1 — Safety guardrails
    GUARDRAIL_CHECK_INTERVAL_SECONDS,
    GUARDRAIL_OVERSHOOT_RATIO,
    GUARDRAIL_STUCK_FLOW_TIMEOUT_SECONDS,
    GUARDRAIL_MQTT_SILENCE_TIMEOUT_SECONDS,
    GUARDRAIL_EXPECTED_DURATION_WARN_RATIO,
    HISTORICAL_FLOW_LOOKBACK_SESSIONS,
    OFF_RETRY_SCHEDULE_SECONDS,
    OFF_RETRY_MAX_DURATION_SECONDS,
    EVENT_SHUTOFF_INITIATED,
    EVENT_SHUTOFF_CONFIRMED,
    EVENT_SHUTOFF_FAILED,
    EVENT_ORPHANED_SESSION_RECOVERED,
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
    last_session_end: Optional[str] = None  # ISO datetime of last session end

    # ───────────────────────────────────────────────────────────────────
    # v3.1 — Safety guardrail tracking (none persisted; recomputed at runtime)
    # ───────────────────────────────────────────────────────────────────

    # Set when any guardrail (or the primary failsafe) decides this valve must
    # turn OFF. While True, the periodic guardrail loop will not re-fire for
    # this valve, and the OFF retry chain manages re-publishing OFF until the
    # device confirms with state=OFF or the retry budget is exhausted.
    shutoff_in_progress: bool = False
    shutoff_reason: str = ""           # human-readable reason
    shutoff_attempt: int = 0           # number of OFF publishes so far
    shutoff_started_ts: float = 0.0    # monotonic time the chain started
    shutoff_cancel_handle: Optional[Callable[[], None]] = None  # next-step timer

    # Tracks when session_liters last increased — used by Guardrail Layer 2
    # (stuck-flow detection). Reset whenever a new session starts.
    last_progress_ts: float = 0.0
    last_progress_value: float = 0.0

    # Pre-computed at start_liters: target_liters / historical_avg_flow * 1.5.
    # Used by Guardrail Layer 4 (expected-duration warning). None means no
    # historical data was available, so the warning is skipped.
    expected_duration_min: Optional[float] = None

    # Whether we have already emitted the Layer 4 warning for the current
    # session. Avoids spam.
    expected_duration_warned: bool = False

    # Whether this session was recovered from a previous HA boot (i.e., it's
    # a brand-new session being created after an in-flight session was found
    # at startup). Currently only used for log labelling.
    recovered_from_orphan: bool = False

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

        # v3.1 — Recover from any orphaned in-flight sessions left over from a
        # previous boot (HA restart, crash, OS reboot mid-irrigation). This
        # MUST happen before we subscribe to MQTT, so that any device state
        # we receive afterwards is treated as a fresh new session and not
        # mistakenly merged with a stale orphan record.
        await self._recover_orphaned_sessions()

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

        # v3.1 — Start the safety guardrail loop. Independent of MQTT, this
        # tick periodically inspects every active session and forces OFF if
        # any of the five guardrails detect a runaway condition.
        self._unsubs.append(
            async_track_time_interval(
                self.hass,
                self._guardrail_tick,
                timedelta(seconds=GUARDRAIL_CHECK_INTERVAL_SECONDS),
            )
        )
        _LOGGER.info(
            "🛡️  Safety guardrail loop started (every %ds)",
            GUARDRAIL_CHECK_INTERVAL_SECONDS,
        )

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

                # Refresh last session start and end
                v.last_session_start = await self.db.get_last_session_start(topic)
                v.last_session_end = await self.db.get_last_session_end(topic)

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

    def _fire_event(self, event_type: str, event_data: Dict) -> None:
        """Thread-safe wrapper for hass.bus.async_fire.

        v3.1.2 — `hass.bus.async_fire` MUST be called from the event loop
        thread. Several call sites (the at-target failsafe in `_on_state`, the
        shutoff confirmation in the state-OFF transition, etc) run from MQTT
        worker threads where this is unsafe and HA throws
        `RuntimeError: ... non-thread-safe operation ...`. That bug bricked
        the failsafe path in v3.1.0 / v3.1.1 — see the audit notes in
        AUDIT-2026-04-08-v3.1.2.md.

        This helper marshals the call onto the event loop via
        `loop.call_soon_threadsafe`, which is safe from any thread.
        """
        self.hass.loop.call_soon_threadsafe(
            self.hass.bus.async_fire, event_type, event_data
        )

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

            # Load last session start and end datetime
            v.last_session_start = await self.db.get_last_session_start(topic)
            v.last_session_end = await self.db.get_last_session_end(topic)

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
                # v3.1 — Track liter progress for Guardrail Layer 2 (stuck flow).
                v.last_progress_ts = now
                v.last_progress_value = v.session_liters

        # FAILSAFE: Check targets even when valve is ON (not just during session_active)
        # This ensures we catch cases where device fails to stop.
        # v3.1 — Skip the at-target failsafe entirely if a shutoff is already
        # in progress; the OFF retry chain owns the valve until confirmed.
        if v.state == "ON" and not v.shutoff_in_progress:
            # FAILSAFE: Check if volume target reached (backup to native device control)
            if v.target_liters and v.target_liters > 0:
                if v.session_liters >= v.target_liters:
                    _LOGGER.warning(
                        "FAILSAFE: Volume target reached for %s: %.2f/%.2f L - initiating shutoff",
                        topic, v.session_liters, v.target_liters
                    )
                    # v3.1 — Hand off to the shutoff state machine instead of
                    # publishing OFF once and clearing target_liters. The
                    # state machine will retry OFF until confirmed and only
                    # then clean up. target_liters stays set so guardrails
                    # remain meaningful.
                    self._initiate_shutoff(v, "volume_target_reached")
                    return
                else:
                    # Debug log to see progress
                    _LOGGER.debug(
                        "Volume run progress for %s: %.2f/%.2f L (%.1f%%), flow: %.2f L/min",
                        topic, v.session_liters, v.target_liters,
                        (v.session_liters / v.target_liters * 100), v.flow_lpm
                    )

                    # v3.1 — Layer 4: warn if elapsed exceeds expected duration.
                    if (
                        v.expected_duration_min is not None
                        and not v.expected_duration_warned
                        and v.session_start_ts > 0
                    ):
                        elapsed_min = (now - v.session_start_ts) / 60.0
                        if elapsed_min > v.expected_duration_min:
                            v.expected_duration_warned = True
                            _LOGGER.warning(
                                "⏱️  Run for %s is taking longer than expected: "
                                "elapsed=%.1fmin, expected≤%.1fmin, progress=%.2f/%.2f L. "
                                "Possible degraded flow (clog, pressure drop). "
                                "Will continue until target or other guardrail fires.",
                                topic, elapsed_min, v.expected_duration_min,
                                v.session_liters, v.target_liters,
                            )

            # FAILSAFE: Check if time target reached (backup to native device control)
            if v.session_end_ts and v.session_start_ts > 0:
                if now >= v.session_end_ts:
                    elapsed_min = (now - v.session_start_ts) / 60.0
                    target_min = (v.session_end_ts - v.session_start_ts) / 60.0
                    _LOGGER.warning(
                        "FAILSAFE: Time target reached for %s: %.2f/%.2f min - initiating shutoff",
                        topic, elapsed_min, target_min
                    )
                    self._initiate_shutoff(v, "time_target_reached")
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
                    # v3.1 — Initialize Layer 2 (stuck-flow) progress tracking.
                    v.last_progress_ts = now
                    v.last_progress_value = 0.0
                    v.expected_duration_warned = False
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
                # v3.1 — If a shutoff was in progress, the device has now
                # confirmed OFF. Clear the retry chain and fire a confirmation
                # event for any external automations listening.
                if v.shutoff_in_progress:
                    elapsed = now - v.shutoff_started_ts if v.shutoff_started_ts > 0 else 0.0
                    _LOGGER.info(
                        "✅ Shutoff confirmed for %s (reason=%s, attempts=%d, elapsed=%.1fs)",
                        topic, v.shutoff_reason, v.shutoff_attempt, elapsed,
                    )
                    self._fire_event(
                        EVENT_SHUTOFF_CONFIRMED,
                        {
                            "valve": topic,
                            "name": v.name,
                            "reason": v.shutoff_reason,
                            "attempts": v.shutoff_attempt,
                            "elapsed_seconds": round(elapsed, 1),
                        },
                    )
                    if v.shutoff_cancel_handle:
                        try:
                            v.shutoff_cancel_handle()
                        except Exception:
                            pass
                        v.shutoff_cancel_handle = None
                    v.shutoff_in_progress = False
                    v.shutoff_reason = ""
                    v.shutoff_attempt = 0
                    v.shutoff_started_ts = 0.0
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

                            # Update last session start and end datetime
                            v.last_session_start = await self.db.get_last_session_start(captured_topic)
                            v.last_session_end = await self.db.get_last_session_end(captured_topic)
                            _LOGGER.debug(f"   last session start: {v.last_session_start}")
                            _LOGGER.debug(f"   last session end: {v.last_session_end}")

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

        # v3.1 — Reset shutoff/guardrail tracking (in case a previous shutoff
        # left dangling state), and pre-compute the expected duration for
        # Layer 4 from historical flow data.
        v.shutoff_in_progress = False
        v.shutoff_reason = ""
        v.shutoff_attempt = 0
        v.shutoff_started_ts = 0.0
        if v.shutoff_cancel_handle:
            try:
                v.shutoff_cancel_handle()
            except Exception:
                pass
            v.shutoff_cancel_handle = None
        v.expected_duration_min = None
        v.expected_duration_warned = False
        self._schedule_task(self._compute_expected_duration(v, v.target_liters))

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
            _LOGGER.warning("FAILSAFE: Backup timer expired for %s - initiating shutoff", topic)
            # v3.1 — Hand off to the retry-aware shutoff machine.
            self._initiate_shutoff(v, "timed_run_backup_timer")
            if v.cancel_handle:
                v.cancel_handle(); v.cancel_handle = None
            v.session_end_ts = None

        v.cancel_handle = async_call_later(self.hass, run_s, _off)

    # ─────────────────────────────────────────────────────────────────────
    # v3.1 — Safety: shutoff retry state machine
    # ─────────────────────────────────────────────────────────────────────

    def _initiate_shutoff(self, v: Valve, reason: str) -> None:
        """Begin the shutoff retry chain for a valve.

        Idempotent: if a shutoff is already in progress for this valve, the new
        request is ignored (the existing chain will run to completion). The
        retry chain publishes OFF, waits, re-checks state, and re-publishes
        with escalating notifications until the device confirms OFF or the
        retry budget is exhausted.
        """
        if v.shutoff_in_progress:
            _LOGGER.debug(
                "Shutoff already in progress for %s (reason=%s); ignoring new request (reason=%s)",
                v.topic, v.shutoff_reason, reason,
            )
            return

        v.shutoff_in_progress = True
        v.shutoff_reason = reason
        v.shutoff_attempt = 0
        v.shutoff_started_ts = time.monotonic()

        _LOGGER.warning(
            "🛑 Initiating shutoff for %s (reason=%s, target=%.2fL, current=%.2fL)",
            v.topic, reason,
            v.target_liters or 0.0,
            v.session_liters,
        )
        self._fire_event(
            EVENT_SHUTOFF_INITIATED,
            {
                "valve": v.topic,
                "name": v.name,
                "reason": reason,
                "target_liters": v.target_liters,
                "session_liters": round(v.session_liters, 2),
            },
        )

        # First attempt is immediate; the chain schedules subsequent retries.
        self._schedule_task(self._attempt_shutoff(v))

    async def _attempt_shutoff(self, v: Valve) -> None:
        """Publish OFF once and schedule the next retry checkpoint, if any.

        Each call corresponds to one attempt. Determines the next checkpoint
        from OFF_RETRY_SCHEDULE_SECONDS based on cumulative elapsed time, or
        gives up and fires the failure event if the budget is exhausted.
        """
        if not v.shutoff_in_progress:
            # Already confirmed OFF (state→OFF transition cleared the flag).
            return

        v.shutoff_attempt += 1
        attempt = v.shutoff_attempt
        elapsed = time.monotonic() - v.shutoff_started_ts

        try:
            await self.async_turn_off(v.topic)
            _LOGGER.warning(
                "🛑 Shutoff attempt #%d for %s published (elapsed=%.1fs, reason=%s)",
                attempt, v.topic, elapsed, v.shutoff_reason,
            )
        except Exception as e:
            _LOGGER.error(
                "Shutoff attempt #%d for %s FAILED to publish: %s",
                attempt, v.topic, e,
            )

        # Escalation by attempt count.
        if attempt == 4:
            _LOGGER.warning(
                "⚠️  Valve %s has not confirmed OFF after %d attempts (%.1fs). Escalating.",
                v.topic, attempt, elapsed,
            )
            self._create_persistent_notification(
                title=f"⚠️ Irrigation valve not stopping: {v.name}",
                message=(
                    f"Valve **{v.name}** ({v.topic}) was asked to shut off "
                    f"({v.shutoff_reason}) but has not confirmed after {attempt} attempts "
                    f"over {elapsed:.0f} seconds. Will keep retrying. "
                    f"Current session: {v.session_liters:.1f} L."
                ),
                notification_id=f"z2m_irrigation_shutoff_{v.topic}",
            )

        # Find the next checkpoint > elapsed.
        next_checkpoint = None
        for s in OFF_RETRY_SCHEDULE_SECONDS:
            if s > elapsed:
                next_checkpoint = s
                break

        if next_checkpoint is None or elapsed >= OFF_RETRY_MAX_DURATION_SECONDS:
            # Give up — fire the critical failure event and persistent notification.
            _LOGGER.error(
                "🚨 GAVE UP on shutoff for %s after %d attempts over %.1fs. "
                "Manual intervention required!",
                v.topic, attempt, elapsed,
            )
            self._fire_event(
                EVENT_SHUTOFF_FAILED,
                {
                    "valve": v.topic,
                    "name": v.name,
                    "reason": v.shutoff_reason,
                    "attempts": attempt,
                    "elapsed_seconds": round(elapsed, 1),
                    "session_liters": round(v.session_liters, 2),
                    "target_liters": v.target_liters,
                },
            )
            self._create_persistent_notification(
                title=f"🚨 CRITICAL: irrigation valve {v.name} won't stop",
                message=(
                    f"Valve **{v.name}** ({v.topic}) failed to acknowledge shutoff "
                    f"after {attempt} attempts over {elapsed:.0f} seconds.\n\n"
                    f"**Manual intervention required.** Check the device "
                    f"(power, Zigbee connectivity), or close the water supply.\n\n"
                    f"Reason: `{v.shutoff_reason}`\n"
                    f"Session: {v.session_liters:.1f} L of {v.target_liters or 'unknown'} L target."
                ),
                notification_id=f"z2m_irrigation_shutoff_{v.topic}",
            )
            # Clear the in-progress flag so future shutoffs can be initiated.
            # We do NOT clear target_liters / session_liters — the next MQTT
            # message (if any) will integrate normally and the at-target
            # failsafe in _on_state can fire again if appropriate.
            v.shutoff_in_progress = False
            v.shutoff_reason = ""
            v.shutoff_attempt = 0
            return

        # Schedule the next attempt.
        delay = max(0.1, next_checkpoint - elapsed)

        async def _retry(_now):
            await self._attempt_shutoff(v)

        v.shutoff_cancel_handle = async_call_later(self.hass, delay, _retry)

    def _create_persistent_notification(self, title: str, message: str,
                                         notification_id: str) -> None:
        """Helper to fire persistent_notification.create. Best-effort; failures
        are swallowed because notifications must never block safety-critical
        code paths.

        v3.1.2 — `hass.services.async_call` and `hass.async_create_task` BOTH
        require the event loop thread. This helper must be safe to call from
        any thread (worker threads in MQTT callbacks, the periodic guardrail
        tick which IS on the loop, etc), so we marshal via
        `loop.call_soon_threadsafe`.
        """
        def _do_create() -> None:
            try:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": title,
                            "message": message,
                            "notification_id": notification_id,
                        },
                        blocking=False,
                    )
                )
            except Exception as e:
                _LOGGER.error("Failed to create persistent notification: %s", e)

        self.hass.loop.call_soon_threadsafe(_do_create)

    # ─────────────────────────────────────────────────────────────────────
    # v3.1 — Safety: periodic guardrail loop
    # ─────────────────────────────────────────────────────────────────────

    async def _guardrail_tick(self, now=None) -> None:
        """Called every GUARDRAIL_CHECK_INTERVAL_SECONDS by HA's time tracker.

        Iterates over every valve and runs the soft guardrail checks. Any
        guardrail that fires triggers _initiate_shutoff(); the retry chain
        and event firing happen there.
        """
        mono = time.monotonic()
        for topic, v in list(self.valves.items()):
            try:
                # Skip valves that are not actively running, or where a
                # shutoff is already underway.
                if not v.session_active or v.shutoff_in_progress:
                    continue
                # Skip valves whose state isn't ON — if HA thinks the valve
                # is OFF, there's nothing to guard against.
                if v.state != "ON":
                    continue

                reason = self._check_guardrails_for_valve(v, mono)
                if reason:
                    _LOGGER.warning(
                        "🛡️  Guardrail '%s' triggered for %s — initiating shutoff",
                        reason, topic,
                    )
                    self._initiate_shutoff(v, reason)
            except Exception as e:
                _LOGGER.error(
                    "Guardrail tick error for %s: %s", topic, e, exc_info=True,
                )

    def _check_guardrails_for_valve(self, v: Valve, now: float) -> Optional[str]:
        """Run all guardrail checks for one valve. Returns the first failing
        reason as a string, or None if all checks pass.

        Layers:
          1. Volume overshoot   — session_liters > target * GUARDRAIL_OVERSHOOT_RATIO
          2. Stuck flow         — no liter progress in GUARDRAIL_STUCK_FLOW_TIMEOUT_SECONDS
          3. MQTT silence       — no MQTT message in GUARDRAIL_MQTT_SILENCE_TIMEOUT_SECONDS
          4. (Layer 4 is informational and lives inline in _on_state, not here.)
        """
        # Layer 1 — volume overshoot
        if (
            v.target_liters
            and v.target_liters > 0
            and v.session_liters > v.target_liters * GUARDRAIL_OVERSHOOT_RATIO
        ):
            return (
                f"overshoot:{v.session_liters:.1f}L>{v.target_liters:.1f}L"
                f"x{GUARDRAIL_OVERSHOOT_RATIO}"
            )

        # Layer 2 — stuck flow
        # Only meaningful for volume runs that haven't reached target.
        if (
            v.target_liters
            and v.target_liters > 0
            and v.session_liters < v.target_liters
            and v.last_progress_ts > 0
        ):
            stuck_for = now - v.last_progress_ts
            if stuck_for >= GUARDRAIL_STUCK_FLOW_TIMEOUT_SECONDS:
                return (
                    f"stuck_flow:{stuck_for:.0f}s_at_{v.session_liters:.2f}L"
                )

        # Layer 3 — MQTT silence (any active session, regardless of trigger)
        if v.last_ts > 0:
            silent_for = now - v.last_ts
            if silent_for >= GUARDRAIL_MQTT_SILENCE_TIMEOUT_SECONDS:
                return f"mqtt_silence:{silent_for:.0f}s"

        return None

    async def _compute_expected_duration(self, v: Valve, target_liters: float) -> None:
        """Set v.expected_duration_min from historical average flow rate. Used
        by Layer 4 (the informational warning). If no history is available,
        leaves expected_duration_min as None — Layer 4 will then be skipped
        for this run."""
        if not target_liters or target_liters <= 0:
            v.expected_duration_min = None
            return
        try:
            avg_flow = await self.db.get_recent_avg_flow(
                v.topic, lookback=HISTORICAL_FLOW_LOOKBACK_SESSIONS
            )
        except Exception as e:
            _LOGGER.debug("Could not compute expected duration for %s: %s", v.topic, e)
            avg_flow = None

        if avg_flow and avg_flow > 0:
            base_min = target_liters / avg_flow
            v.expected_duration_min = base_min * GUARDRAIL_EXPECTED_DURATION_WARN_RATIO
            _LOGGER.debug(
                "Expected duration for %s: target=%.1fL, avg_flow=%.2fL/min, "
                "warn_at=%.1fmin (base %.1f * %.1f)",
                v.topic, target_liters, avg_flow, v.expected_duration_min,
                base_min, GUARDRAIL_EXPECTED_DURATION_WARN_RATIO,
            )
        else:
            v.expected_duration_min = None
            _LOGGER.debug(
                "No flow history for %s — Layer 4 (expected duration) disabled for this run",
                v.topic,
            )

    # ─────────────────────────────────────────────────────────────────────
    # v3.1 — Safety: orphaned in-flight session recovery
    # v3.1.1 — Two-phase: DB cleanup now, force-OFF + notification deferred
    # ─────────────────────────────────────────────────────────────────────

    async def _recover_orphaned_sessions(self) -> None:
        """Run once at startup. Find any sessions that were started but not
        ended (HA crashed/restarted mid-run) and reconcile them in two phases:

        PHASE 1 (synchronous, runs during async_start):
          - Mark every orphan session as ended in the local DB.

        PHASE 2 (deferred to EVENT_HOMEASSISTANT_STARTED):
          - Dedupe orphans by valve_topic.
          - Publish OFF once per unique valve via MQTT.
          - Fire one EVENT_ORPHANED_SESSION_RECOVERED event per unique valve.
          - Create a single persistent notification summarising the recovery.

        Why two phases (v3.1.1 fix):
          During async_start, neither the MQTT integration nor the
          persistent_notification service are necessarily ready yet, so any
          attempt to use them at that point silently fails. Phase 2 waits for
          HA to be fully booted before performing the actions that depend on
          other integrations.

        This is the safest possible behavior: after a restart we cannot know
        the physical state of the valves, so we assume the worst and force
        them all closed. The user can manually restart irrigation if needed.
        """
        try:
            orphans = await self.db.get_in_flight_sessions()
        except Exception as e:
            _LOGGER.error("Failed to query in-flight sessions on startup: %s", e)
            return

        if not orphans:
            _LOGGER.debug("No orphaned in-flight sessions found at startup")
            return

        _LOGGER.warning(
            "⚠️  Found %d orphaned in-flight session(s) at startup — closing them "
            "in DB now; force-OFF and notification deferred until HA fully started",
            len(orphans),
        )

        # ─────────────────────────────────────────────────────────────────
        # PHASE 1 — DB cleanup (safe to do during async_start)
        #
        # We mark every orphan as ended in the local SQLite DB right now. This
        # is a pure local operation that doesn't depend on any other HA
        # integration, so it's safe to run during async_start.
        # ─────────────────────────────────────────────────────────────────
        for o in orphans:
            session_id = o.get("session_id")
            try:
                await self.db.end_session(
                    session_id,
                    duration_minutes=0.0,
                    volume_liters=0.0,
                    avg_flow_rate=0.0,
                )
            except Exception as e:
                _LOGGER.error(
                    "Recovery: failed to mark orphaned session %s as ended: %s",
                    session_id, e,
                )

        # ─────────────────────────────────────────────────────────────────
        # PHASE 2 — force-OFF + notification (deferred to STARTED)
        #
        # The MQTT integration and the persistent_notification service are
        # NOT yet available during async_start (this was a v3.1.0 bug —
        # see PR#2 follow-up). We defer the actions that need them until
        # the EVENT_HOMEASSISTANT_STARTED event fires, which is when HA is
        # fully booted and all integrations are ready.
        #
        # We also dedupe by valve_topic at this point — the v3.1.0 release
        # had a case where 91 orphaned sessions across 4 valves resulted in
        # 91 redundant OFF publishes. Now we publish OFF once per unique
        # valve, regardless of how many orphan sessions belonged to it.
        # ─────────────────────────────────────────────────────────────────
        unique_topics: Dict[str, str] = {}  # topic -> friendly name
        for o in orphans:
            topic = o.get("valve_topic")
            if topic and topic not in unique_topics:
                unique_topics[topic] = o.get("valve_name") or topic

        async def _deferred_off_and_notify(_event=None) -> None:
            _LOGGER.warning(
                "🛑 HA started — running deferred orphan recovery: force-OFF for "
                "%d unique valve(s) (from %d orphan session(s))",
                len(unique_topics), len(orphans),
            )
            for topic, name in unique_topics.items():
                try:
                    await self.async_turn_off(topic)
                    _LOGGER.warning(
                        "🛑 Recovery: published OFF for orphaned valve %s (deferred)",
                        topic,
                    )
                except Exception as e:
                    _LOGGER.error(
                        "Recovery: failed to publish deferred OFF for %s: %s",
                        topic, e,
                    )
                # Fire one event per unique valve.
                self._fire_event(
                    EVENT_ORPHANED_SESSION_RECOVERED,
                    {
                        "valve": topic,
                        "name": name,
                        "deferred": True,
                        "orphan_count": sum(
                            1 for o in orphans if o.get("valve_topic") == topic
                        ),
                    },
                )

            # Persistent notification — summarise. Cap the names list at 5
            # to keep the notification readable for large orphan counts.
            names_list = list(unique_topics.values())
            if len(names_list) <= 5:
                names_str = ", ".join(names_list)
            else:
                names_str = ", ".join(names_list[:5]) + f", and {len(names_list) - 5} more"

            self._create_persistent_notification(
                title="🛡️ z2m_irrigation: orphaned sessions recovered",
                message=(
                    f"At startup, **{len(orphans)}** irrigation session(s) across "
                    f"**{len(unique_topics)}** valve(s) were found in an in-flight "
                    f"state. This means Home Assistant restarted while irrigation "
                    f"was running, OR these sessions accumulated from past "
                    f"restarts before v3.1.\n\n"
                    f"Affected valves: **{names_str}**\n\n"
                    f"All affected valves have been sent a force-OFF command. "
                    f"Please verify physically that the valves have actually "
                    f"closed and that no over-watering occurred."
                ),
                notification_id="z2m_irrigation_orphan_recovery",
            )

        # Register the deferred handler. Two cases:
        #
        # (a) Normal HA boot: we're called from async_start which runs while
        #     CoreState is "starting". Listen for EVENT_HOMEASSISTANT_STARTED
        #     which fires when HA finishes booting all integrations.
        #
        # (b) Config reload (rare): the integration is being re-set up while
        #     HA is already running. In this case STARTED has already fired
        #     and won't fire again, so we run the deferred work right away.
        if self.hass.state == CoreState.running:
            _LOGGER.debug("HA already running — running deferred recovery now")
            self._schedule_task(_deferred_off_and_notify())
        else:
            _LOGGER.debug(
                "Registered deferred orphan recovery for EVENT_HOMEASSISTANT_STARTED"
            )
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, _deferred_off_and_notify
            )
