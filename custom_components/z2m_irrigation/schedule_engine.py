"""Scheduler engine for z2m_irrigation.

v4.0-alpha-2 — the first real scheduler implementation since the dead
Supabase one was deleted in v4.0-alpha-1. Architecture per Stage 2:

  * Per-minute tick (`async_track_time_change(second=0)`) — examines all
    enabled schedules and fires any whose `time` matches now in the local
    timezone, on a matching weekday.
  * Sequential FIFO run queue — only one valve runs at a time. Multi-zone
    schedules enqueue all their zones; the queue runner publishes one
    valve, waits for it to actually open, waits for it to close (via
    Valve.session_active polling), then advances. A 5s gap between zones
    gives the device time to fully settle.
  * Run-gate checks before each fire: master_enable, panic, skip-today,
    schedule.enabled, weather skip thresholds, valve membership in the
    smart cycle.
  * Catch-up window — if HA starts up within 30 minutes of a schedule's
    fire-time-today and that schedule has not run today yet, fire it.
    Outside that window the missed run is logged as
    `skipped_catchup_window` and the user can manually re-trigger.
  * Cancellation — `cancel_all()` clears the queue. Panic auto-cancels.
    Toggling master_enable OFF stops new schedules from firing but does
    NOT cancel an in-progress queue (existing run completes).
  * No persistence of in-flight queue across HA restart — Stage 2
    explicitly chose abandon-on-restart for safety. The schedule's
    `last_run_at` is updated as soon as the engine starts firing, so
    catch-up logic does not double-fire.

The engine does not own per-valve state — it just calls
`ValveManager.start_liters` (or `start_timed`) and reads
`Valve.session_active` to know when each zone is done. All existing
guardrails, panic logic, and per-valve sensors continue to work
unchanged whether a session was started by the engine or a manual call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from typing import Callable, Deque, List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    DAYS_OF_WEEK,
    SCHEDULE_MODE_SMART,
    SCHEDULE_MODE_FIXED,
    SCHEDULE_CATCHUP_WINDOW_MINUTES,
    SCHEDULE_INTER_ZONE_GAP_SECONDS,
    SCHEDULE_RUN_START_TIMEOUT_SECONDS,
    SCHEDULE_QUEUE_POLL_SECONDS,
    OUTCOME_RAN,
    OUTCOME_RAN_PARTIAL,
    OUTCOME_SKIPPED_RAIN,
    OUTCOME_SKIPPED_FORECAST,
    OUTCOME_SKIPPED_DISABLED,
    OUTCOME_SKIPPED_PAUSED,
    OUTCOME_SKIPPED_PANIC,
    OUTCOME_SKIPPED_TODAY,
    OUTCOME_SKIPPED_NO_ZONES,
    OUTCOME_SKIPPED_CATCHUP_WINDOW,
    OUTCOME_ERROR,
    EVENT_SCHEDULE_FIRED,
    EVENT_SCHEDULE_SKIPPED,
    EVENT_SMART_RUN_STARTED,
    SIG_GLOBAL_UPDATE,
)
from .zone_store import Schedule, ZoneStore
from .calculator import CalculatorResult

if TYPE_CHECKING:
    from .manager import ValveManager

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Run queue item
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class QueueItem:
    """A single zone-run waiting to be executed by the queue runner.

    `trigger_label` flows through to the eventual database session row's
    `trigger_type` so the dashboard can distinguish manual / scheduled /
    smart-cycle / catch-up runs in the history view.
    """
    zone: str
    liters: float
    trigger_label: str
    schedule_id: Optional[str] = None  # set when this item was queued by a schedule


# ─────────────────────────────────────────────────────────────────────────────
# ScheduleEngine
# ─────────────────────────────────────────────────────────────────────────────


class ScheduleEngine:
    """Owns the schedule tick loop and the sequential run queue.

    Lifecycle is driven by `ValveManager.async_start` / `async_stop`,
    which call `start()` and `stop()` on this engine. The engine holds a
    weak reference to the manager (passed in the constructor) and uses it
    to read valve state, fire OFF commands, and read the cached
    `today_calculation` for smart runs.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        manager: "ValveManager",
        zone_store: ZoneStore,
    ) -> None:
        self.hass = hass
        self.mgr = manager
        self.store = zone_store

        self._unsub_tick: Optional[Callable[[], None]] = None
        self._queue: Deque[QueueItem] = deque()
        self._runner_task: Optional[asyncio.Task] = None

        # In-memory "skip-today" flag. Date is stored so the flag
        # auto-clears at the next local-time midnight (we just compare
        # against `_local_today()` on every check). Per Stage 2 this is
        # not persisted across HA restart — user can re-call skip_today
        # if they need to.
        self._skip_today_date: Optional[date] = None

        # Set of schedule_ids that have already fired today, so the
        # per-minute tick doesn't double-fire on the same minute window
        # and the catch-up logic doesn't reschedule something that
        # already ran. Auto-clears at midnight (compared against
        # `_fired_today_date`).
        self._fired_today: set[str] = set()
        self._fired_today_date: Optional[date] = None

    # ─────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Subscribe to the per-minute tick and run an initial catch-up."""
        if self._unsub_tick is not None:
            return
        self._unsub_tick = async_track_time_change(
            self.hass, self._on_minute, second=0,
        )
        _LOGGER.info("⏰ ScheduleEngine started (per-minute tick + catch-up)")
        # Defer catch-up until after MQTT + valves are ready. The manager's
        # async_start path runs `engine.start()` before subscribing to MQTT,
        # so we schedule catch-up onto the loop instead of running inline.
        self.hass.async_create_task(self._initial_catchup())

    def stop(self) -> None:
        """Cancel tick + queue runner. Existing in-flight run is left alone."""
        if self._unsub_tick is not None:
            try:
                self._unsub_tick()
            except Exception:
                pass
            self._unsub_tick = None
        if self._runner_task is not None and not self._runner_task.done():
            self._runner_task.cancel()
        _LOGGER.info("⏰ ScheduleEngine stopped")

    # ─────────────────────────────────────────────────────────────────────
    # Time helpers
    # ─────────────────────────────────────────────────────────────────────

    def _local_now(self) -> datetime:
        return dt_util.now()

    def _local_today(self) -> date:
        return self._local_now().date()

    def _refresh_fired_today(self) -> None:
        """Reset the per-day fired set if the local date has rolled over."""
        today = self._local_today()
        if self._fired_today_date != today:
            self._fired_today.clear()
            self._fired_today_date = today

    def _parse_schedule_time(self, sch: Schedule) -> Optional[dt_time]:
        """Parse a schedule's `time` field.

        v4.0-rc-3 (F-B): if the time field is a sun-relative expression
        (`sunrise`, `sunset`, with optional `±N` minute offset), this
        returns None — callers should use `_resolve_schedule_datetime()`
        instead which knows how to look up the sun integration's
        `next_rising` / `next_setting` attributes for the target date.

        Plain `HH:MM` returns a naive `dt_time`.
        """
        if not sch.time:
            return None
        if self._is_sun_relative(sch.time):
            return None  # caller must use _resolve_schedule_datetime
        try:
            hh, mm = sch.time.split(":", 1)
            return dt_time(int(hh), int(mm))
        except Exception:
            _LOGGER.warning("Schedule %s has invalid time '%s'", sch.id, sch.time)
            return None

    # v4.0-rc-3 (F-B) — sun-relative time support
    #
    # Schedule.time can now be one of:
    #   "06:00"          — fixed local time (24-hour, HA system TZ)
    #   "sunrise"        — at local sunrise
    #   "sunrise-45"     — 45 minutes before sunrise
    #   "sunrise+30"     — 30 minutes after sunrise
    #   "sunset"         — at local sunset
    #   "sunset+15"      — 15 minutes after sunset
    #   "dawn"           — civil dawn (start of civil twilight)
    #   "dusk"           — civil dusk (end of civil twilight)
    #   "noon"           — solar noon (highest sun position)
    #   "midnight"       — solar midnight
    # All sun events accept an optional ±N minute offset and an
    # optional trailing 'm' (e.g. "dusk+10m").
    #
    # The engine resolves sun-relative times by reading the corresponding
    # `sun.sun.attributes.next_*` field, which HA's `sun` integration
    # keeps current using the system location (Settings → System →
    # General → Edit location). Move HA to a new location and the
    # times automatically update — nothing in this engine is tied to
    # a specific lat/lon.
    SUN_EVENT_ATTR_MAP = {
        "sunrise": "next_rising",
        "sunset": "next_setting",
        "dawn": "next_dawn",
        "dusk": "next_dusk",
        "noon": "next_noon",
        "midnight": "next_midnight",
    }

    @staticmethod
    def _is_sun_relative(time_str: str) -> bool:
        s = (time_str or "").strip().lower()
        for event in ScheduleEngine.SUN_EVENT_ATTR_MAP:
            if s.startswith(event):
                return True
        return False

    @staticmethod
    def _parse_sun_offset(time_str: str) -> tuple[Optional[str], int]:
        """Parse a sun-relative time string into (event, minutes).

        Returns (None, 0) on parse failure. `event` is one of the keys
        in `SUN_EVENT_ATTR_MAP`. `minutes` is the signed offset
        (negative = before, positive = after).
        """
        import re
        s = (time_str or "").strip().lower()
        events_alt = "|".join(ScheduleEngine.SUN_EVENT_ATTR_MAP.keys())
        m = re.match(rf"^({events_alt})\s*([+-]?\s*\d+)?\s*m?$", s)
        if not m:
            return (None, 0)
        event = m.group(1)
        offset_str = (m.group(2) or "0").replace(" ", "")
        try:
            offset = int(offset_str)
        except Exception:
            offset = 0
        return (event, offset)

    def _resolve_schedule_datetime(
        self, sch: Schedule, target_date: date,
    ) -> Optional[datetime]:
        """Resolve a schedule's fire-time to a concrete tz-aware datetime
        on `target_date`. Handles both fixed `HH:MM` and sun-relative.

        For sun-relative: reads `sun.sun.attributes.next_rising` /
        `next_setting`, which is always the NEXT one. If `target_date`
        is today and the event is in the future, that's our answer.
        Otherwise we approximate by using the same time-of-day on
        `target_date` (close enough — sunrise drifts by ~1-2 minutes/day).
        """
        local_now = self._local_now()
        tz = local_now.tzinfo

        if not sch.time:
            return None

        if not self._is_sun_relative(sch.time):
            # Fixed HH:MM path
            try:
                hh, mm = sch.time.split(":", 1)
                return datetime.combine(
                    target_date, dt_time(int(hh), int(mm)), tzinfo=tz,
                )
            except Exception:
                return None

        # Sun-relative path
        event, offset_min = self._parse_sun_offset(sch.time)
        if event is None:
            _LOGGER.warning(
                "Schedule %s has invalid sun-relative time %r",
                sch.id, sch.time,
            )
            return None

        sun = self.hass.states.get("sun.sun")
        if sun is None or not sun.attributes:
            _LOGGER.warning(
                "Schedule %s wants sun-relative time but sun.sun is unavailable",
                sch.id,
            )
            return None

        # rc-3 (F-B): map any of the 6 supported events to the
        # corresponding `sun.sun` attribute name.
        attr_key = self.SUN_EVENT_ATTR_MAP.get(event)
        if attr_key is None:
            return None
        attr_val = sun.attributes.get(attr_key)
        if not attr_val:
            return None
        try:
            sun_dt = datetime.fromisoformat(str(attr_val).replace("Z", "+00:00"))
        except Exception:
            return None
        sun_local = sun_dt.astimezone(tz)

        # If target_date matches the next sun event, use it directly.
        # Otherwise project the same hour:minute onto target_date — sun
        # drift over a week is small enough that the per-minute tick
        # will catch the actual fire on the day.
        if sun_local.date() == target_date:
            return sun_local + timedelta(minutes=offset_min)

        approx = datetime.combine(
            target_date,
            dt_time(sun_local.hour, sun_local.minute),
            tzinfo=tz,
        )
        return approx + timedelta(minutes=offset_min)

    def _matches_today(self, sch: Schedule) -> bool:
        if not sch.days:
            return True  # empty list = every day
        today_token = DAYS_OF_WEEK[self._local_now().weekday()]
        return today_token in sch.days

    # ─────────────────────────────────────────────────────────────────────
    # Per-minute tick
    # ─────────────────────────────────────────────────────────────────────

    async def _on_minute(self, now: datetime) -> None:
        """Called every minute on second=0. Fires any schedules due now."""
        self._refresh_fired_today()
        try:
            schedules = self.store.all_schedules_typed()
        except Exception as e:
            _LOGGER.error("ScheduleEngine: failed to read schedules: %s", e)
            return

        local_now = self._local_now()
        current_hm = local_now.strftime("%H:%M")

        for sch in schedules:
            if not sch.enabled:
                continue
            if sch.id in self._fired_today:
                continue
            if not self._matches_today(sch):
                continue

            # v4.0-rc-3 (F-B): handle both fixed HH:MM and sun-relative
            # times. For sun-relative, resolve to today's actual fire
            # time and compare to current minute.
            if self._is_sun_relative(sch.time):
                target_dt = self._resolve_schedule_datetime(sch, local_now.date())
                if target_dt is None:
                    continue
                if target_dt.strftime("%H:%M") != current_hm:
                    continue
            else:
                if sch.time != current_hm:
                    continue

            self._fired_today.add(sch.id)
            await self._fire_schedule(sch, trigger="scheduled")

    # ─────────────────────────────────────────────────────────────────────
    # Catch-up on startup
    # ─────────────────────────────────────────────────────────────────────

    async def _initial_catchup(self) -> None:
        """Fire any enabled schedule whose fire-time was within the last
        SCHEDULE_CATCHUP_WINDOW_MINUTES and which has not already run today.

        Skips schedules whose fire-time was earlier today than the catch-up
        window — those are recorded as `skipped_catchup_window` and the user
        can manually re-trigger via `run_schedule_now` if desired.
        """
        # Wait briefly so the manager has finished discovering valves and
        # the calculator has at least one cache populate. The exact delay
        # is not load-bearing — schedules are time-of-day, not millisecond.
        await asyncio.sleep(5)

        self._refresh_fired_today()
        local_now = self._local_now()
        today = local_now.date()

        try:
            schedules = self.store.all_schedules_typed()
        except Exception as e:
            _LOGGER.error("ScheduleEngine: catch-up read failed: %s", e)
            return

        for sch in schedules:
            if not sch.enabled:
                continue
            if not self._matches_today(sch):
                continue

            # v4.0-rc-3 (F-B): use the unified resolver which handles
            # both fixed HH:MM and sun-relative time formats.
            sch_dt = self._resolve_schedule_datetime(sch, today)
            if sch_dt is None:
                continue
            if sch_dt > local_now:
                continue  # still in the future, the per-minute tick will get it

            # Already ran today?
            if sch.last_run_at:
                try:
                    last = datetime.fromisoformat(sch.last_run_at.replace("Z", "+00:00"))
                    if last.astimezone(local_now.tzinfo).date() == today:
                        self._fired_today.add(sch.id)
                        continue
                except Exception:
                    pass

            minutes_late = (local_now - sch_dt).total_seconds() / 60.0
            if minutes_late > SCHEDULE_CATCHUP_WINDOW_MINUTES:
                _LOGGER.info(
                    "⏰ Schedule '%s' (%s) missed by %.0f min — outside catch-up "
                    "window (%d min). Marking skipped.",
                    sch.name, sch.id, minutes_late, SCHEDULE_CATCHUP_WINDOW_MINUTES,
                )
                await self._record_skip(sch, OUTCOME_SKIPPED_CATCHUP_WINDOW)
                self._fired_today.add(sch.id)
                continue

            _LOGGER.info(
                "⏰ Catch-up firing schedule '%s' (%s) — %.0f min late",
                sch.name, sch.id, minutes_late,
            )
            self._fired_today.add(sch.id)
            await self._fire_schedule(sch, trigger="catchup")

    # ─────────────────────────────────────────────────────────────────────
    # Schedule firing — gate checks and zone enqueue
    # ─────────────────────────────────────────────────────────────────────

    async def _fire_schedule(self, sch: Schedule, *, trigger: str) -> None:
        """Apply pre-run gates and either enqueue or record skip.

        Pre-run gate order:
          1. master_enable
          2. panic active
          3. skip_today flag
          4. weather skip thresholds (rain today, rain forecast 24h)
          5. zone resolution + min-run filter
        """
        # 1. master enable
        if not self.mgr.master_enable:
            _LOGGER.info("⏸️  Schedule '%s' skipped: master_enable OFF", sch.name)
            await self._record_skip(sch, OUTCOME_SKIPPED_PAUSED)
            return

        # 2. panic
        if self.mgr.panic.active:
            _LOGGER.warning(
                "🚨 Schedule '%s' skipped: panic state active (%s)",
                sch.name, self.mgr.panic.reason,
            )
            await self._record_skip(sch, OUTCOME_SKIPPED_PANIC)
            return

        # 3. skip-today
        if self._skip_today_date is not None and self._skip_today_date == self._local_today():
            _LOGGER.info("⏭️  Schedule '%s' skipped: skip_today flag set", sch.name)
            await self._record_skip(sch, OUTCOME_SKIPPED_TODAY)
            return

        # 4. weather skip thresholds — only smart mode honors these. Fixed
        # mode is "the user explicitly asked for N liters", so we don't
        # second-guess them with weather.
        if sch.mode == SCHEDULE_MODE_SMART:
            calc = await self._ensure_recent_calculation()
            rain_today = calc.weather.effective_rain_today if calc else 0.0
            fc24 = calc.weather.effective_fc24 if calc else 0.0

            if rain_today >= self.mgr.global_skip_rain_threshold_mm:
                _LOGGER.info(
                    "🌧️  Schedule '%s' skipped: rain today %.1f mm ≥ threshold %.1f mm",
                    sch.name, rain_today, self.mgr.global_skip_rain_threshold_mm,
                )
                await self._record_skip(sch, OUTCOME_SKIPPED_RAIN)
                return
            if fc24 >= self.mgr.global_skip_forecast_threshold_mm:
                _LOGGER.info(
                    "⛈️  Schedule '%s' skipped: rain forecast 24h %.1f mm ≥ threshold %.1f mm",
                    sch.name, fc24, self.mgr.global_skip_forecast_threshold_mm,
                )
                await self._record_skip(sch, OUTCOME_SKIPPED_FORECAST)
                return

        # 5. zone resolution
        items = self._resolve_zones(sch)
        if not items:
            _LOGGER.info(
                "⏭️  Schedule '%s' skipped: no runnable zones after filtering",
                sch.name,
            )
            await self._record_skip(sch, OUTCOME_SKIPPED_NO_ZONES)
            return

        # All gates passed — enqueue and fire the bus event.
        _LOGGER.info(
            "▶️  Firing schedule '%s' (id=%s mode=%s trigger=%s) → %d zone(s), %.1f L total",
            sch.name, sch.id, sch.mode, trigger, len(items),
            sum(it.liters for it in items),
        )
        self.mgr._fire_event(
            EVENT_SCHEDULE_FIRED,
            {
                "schedule_id": sch.id,
                "schedule_name": sch.name,
                "mode": sch.mode,
                "trigger": trigger,
                "zones": [it.zone for it in items],
                "total_liters": round(sum(it.liters for it in items), 2),
            },
        )
        await self.store.mark_schedule_run(sch.id, outcome=OUTCOME_RAN)
        # v4.0-alpha-3 — record fire event in the global timeline so the
        # Insight tab can render the "what happened" chart.
        try:
            await self.store.record_schedule_event(
                kind="fired",
                schedule_id=sch.id,
                schedule_name=sch.name,
                outcome=OUTCOME_RAN,
                mode=sch.mode,
                trigger=trigger,
                zones=[it.zone for it in items],
                total_liters=sum(it.liters for it in items),
            )
        except Exception as e:
            _LOGGER.warning("Failed to record schedule fire event: %s", e)
        for item in items:
            self._queue.append(item)
        self._ensure_runner()

    async def _ensure_recent_calculation(self) -> Optional[CalculatorResult]:
        """Force a calculator refresh and return the result.

        We always recompute on schedule fire so the inputs are fresh for
        the gate decision (rather than trusting whatever the 15-min loop
        last cached). The result is also stamped into the manager's
        `today_calculation` cache as a side effect.
        """
        try:
            return await self.mgr.recalculate_today()
        except Exception as e:
            _LOGGER.error("Calculator refresh in fire flow failed: %s", e)
            return self.mgr.today_calculation

    def _resolve_zones(self, sch: Schedule) -> List[QueueItem]:
        """Translate a schedule into concrete QueueItems.

        Smart mode:
          * Use the calculator result. Per-zone liters come from there.
          * If `sch.zones` is empty → all zones marked in_smart_cycle.
          * If `sch.zones` is set → those zones, only if they're known
            and (in smart mode) flagged in_smart_cycle.
          * Per-zone min-run filter (zone override or global) applies.

        Fixed mode:
          * Every named zone gets the same `fixed_liters_per_zone`.
          * Empty `sch.zones` is treated as "no zones" → skipped.
        """
        if sch.mode == SCHEDULE_MODE_FIXED:
            liters = float(sch.fixed_liters_per_zone or 0)
            if liters <= 0 or not sch.zones:
                return []
            out: List[QueueItem] = []
            for zone in sch.zones:
                if zone not in self.mgr.valves:
                    _LOGGER.warning(
                        "Schedule %s lists unknown zone '%s' — skipping",
                        sch.id, zone,
                    )
                    continue
                out.append(QueueItem(
                    zone=zone, liters=liters,
                    trigger_label=f"schedule_fixed:{sch.id}",
                    schedule_id=sch.id,
                ))
            return out

        # Smart mode
        calc = self.mgr.today_calculation
        if calc is None:
            _LOGGER.warning(
                "Schedule %s smart mode but no calculator result available",
                sch.id,
            )
            return []
        # If schedule names specific zones, intersect with calc rows.
        wanted = set(sch.zones) if sch.zones else None
        out = []
        for zc in calc.zones:
            if zc.skipped:
                continue
            if wanted is not None and zc.zone not in wanted:
                continue
            if zc.zone not in self.mgr.valves:
                continue
            out.append(QueueItem(
                zone=zc.zone,
                liters=zc.liters,
                trigger_label=f"schedule_smart:{sch.id}",
                schedule_id=sch.id,
            ))
        return out

    async def _record_skip(self, sch: Schedule, outcome: str) -> None:
        """Stamp last_run_outcome, fire the SKIPPED bus event, and append
        to the global timeline.
        """
        await self.store.mark_schedule_run(sch.id, outcome=outcome)
        # v4.0-alpha-3 — record skip event in the global timeline.
        try:
            await self.store.record_schedule_event(
                kind="skipped",
                schedule_id=sch.id,
                schedule_name=sch.name,
                outcome=outcome,
                mode=sch.mode,
                trigger=None,
                zones=[],
                total_liters=None,
            )
        except Exception as e:
            _LOGGER.warning("Failed to record schedule skip event: %s", e)
        self.mgr._fire_event(
            EVENT_SCHEDULE_SKIPPED,
            {
                "schedule_id": sch.id,
                "schedule_name": sch.name,
                "outcome": outcome,
            },
        )
        # Notify the global sensors so the dashboard updates the schedule list.
        self.mgr._notify_global()

    # ─────────────────────────────────────────────────────────────────────
    # Public manual entrypoints — used by services
    # ─────────────────────────────────────────────────────────────────────

    async def run_smart_now(self, zones: Optional[List[str]] = None) -> int:
        """Ad-hoc smart cycle. Returns the number of zones queued.

        Same gate checks as a scheduled smart fire (master enable, panic,
        weather thresholds), but ignores the skip-today flag — the user
        explicitly asked.
        """
        if not self.mgr.master_enable:
            _LOGGER.info("run_smart_now: skipped, master_enable OFF")
            return 0
        if self.mgr.panic.active:
            _LOGGER.warning("run_smart_now: skipped, panic active")
            return 0

        calc = await self._ensure_recent_calculation()
        if calc is None:
            _LOGGER.warning("run_smart_now: no calculator data, skipping")
            return 0

        wanted = set(zones) if zones else None
        items: List[QueueItem] = []
        for zc in calc.zones:
            if zc.skipped:
                continue
            if wanted is not None and zc.zone not in wanted:
                continue
            if zc.zone not in self.mgr.valves:
                continue
            items.append(QueueItem(
                zone=zc.zone, liters=zc.liters,
                trigger_label="manual_smart",
                schedule_id=None,
            ))

        if not items:
            _LOGGER.info("run_smart_now: nothing to run")
            return 0

        _LOGGER.info(
            "▶️  run_smart_now: queuing %d zone(s), %.1f L total",
            len(items), sum(it.liters for it in items),
        )
        self.mgr._fire_event(
            EVENT_SMART_RUN_STARTED,
            {
                "trigger": "manual",
                "zones": [it.zone for it in items],
                "total_liters": round(sum(it.liters for it in items), 2),
            },
        )
        for item in items:
            self._queue.append(item)
        self._ensure_runner()
        return len(items)

    async def run_schedule_now(self, schedule_id: str) -> bool:
        """Force-fire a specific schedule, ignoring its time/day filter
        but still applying all the safety gates."""
        sch = self.store.get_schedule(schedule_id)
        if sch is None:
            _LOGGER.warning("run_schedule_now: %s not found", schedule_id)
            return False
        await self._fire_schedule(sch, trigger="manual")
        return True

    def set_skip_today(self, enabled: bool) -> None:
        """Set or clear the skip-today flag for today's local date."""
        if enabled:
            self._skip_today_date = self._local_today()
            _LOGGER.info("⏭️  skip_today set for %s", self._skip_today_date)
        else:
            self._skip_today_date = None
            _LOGGER.info("⏭️  skip_today cleared")
        self.mgr._notify_global()

    @property
    def skip_today_active(self) -> bool:
        return (
            self._skip_today_date is not None
            and self._skip_today_date == self._local_today()
        )

    def cancel_all(self) -> int:
        """Empty the run queue. Returns the number of items dropped.

        Does NOT cancel an in-flight valve session — the queue runner
        will see the empty queue and exit cleanly after the current zone
        finishes. To cancel the in-flight session call
        `mgr.async_turn_off(topic)` separately.
        """
        n = len(self._queue)
        self._queue.clear()
        if n:
            _LOGGER.info("🛑 ScheduleEngine: cancel_all dropped %d queued zone(s)", n)
        return n

    def queue_snapshot(self) -> List[dict]:
        """Return a JSON-friendly view of the queue for the sensor."""
        return [
            {
                "zone": it.zone,
                "liters": round(it.liters, 2),
                "trigger": it.trigger_label,
                "schedule_id": it.schedule_id,
            }
            for it in self._queue
        ]

    # ─────────────────────────────────────────────────────────────────────
    # Queue runner
    # ─────────────────────────────────────────────────────────────────────

    def _ensure_runner(self) -> None:
        """Start the queue runner task if it isn't already running."""
        if self._runner_task is not None and not self._runner_task.done():
            return
        self._runner_task = self.hass.async_create_task(self._queue_runner())
        self.mgr._notify_global()

    async def _queue_runner(self) -> None:
        """Sequentially execute queue items.

        For each item:
          1. Bail out if any gate now blocks (panic, master_enable off)
          2. Call manager.start_liters(...)
          3. Wait up to RUN_START_TIMEOUT for session_active to flip ON
          4. Poll session_active until it flips OFF
          5. Brief inter-zone gap, then advance

        The runner exits when the queue is empty.
        """
        try:
            while self._queue:
                # Re-check global gates between zones — panic during a
                # multi-zone schedule should drop the rest, not just the
                # in-progress one.
                if self.mgr.panic.active:
                    _LOGGER.warning(
                        "🚨 Queue runner: panic active, dropping %d remaining zone(s)",
                        len(self._queue),
                    )
                    self._queue.clear()
                    break
                if not self.mgr.master_enable:
                    _LOGGER.info(
                        "⏸️  Queue runner: master_enable OFF, dropping %d remaining zone(s)",
                        len(self._queue),
                    )
                    self._queue.clear()
                    break

                item = self._queue[0]
                v = self.mgr.valves.get(item.zone)
                if v is None:
                    _LOGGER.warning(
                        "Queue runner: valve '%s' disappeared, skipping", item.zone,
                    )
                    self._queue.popleft()
                    continue

                # v4.0-rc-1 — wait for ANY currently-running valve to
                # finish before publishing the next zone. Without this
                # check, a manual session that the user kicked off via
                # the switch entity would run concurrently with the
                # next queued zone, opening two valves on the same
                # water supply and skewing both flow measurements.
                # The check is per-valve session_active, so it covers
                # both manual switch toggles and prior queue items.
                blocked_by = next(
                    (other for other in self.mgr.valves.values()
                     if other.session_active and other.topic != item.zone),
                    None,
                )
                if blocked_by is not None:
                    _LOGGER.info(
                        "⏸️  Queue runner: waiting for in-flight session on %s "
                        "before starting %s",
                        blocked_by.topic, item.zone,
                    )
                    while blocked_by.session_active:
                        if self.mgr.panic.active or not self.mgr.master_enable:
                            _LOGGER.warning(
                                "Queue runner: gate flipped while waiting for "
                                "%s, dropping queue", blocked_by.topic,
                            )
                            self._queue.clear()
                            break
                        await asyncio.sleep(SCHEDULE_QUEUE_POLL_SECONDS)
                    if not self._queue:
                        break
                    # Brief settle gap before opening the next valve
                    await asyncio.sleep(SCHEDULE_INTER_ZONE_GAP_SECONDS)

                _LOGGER.info(
                    "▶️  Queue runner: starting %s for %.2f L (trigger=%s)",
                    item.zone, item.liters, item.trigger_label,
                )
                try:
                    self.mgr.start_liters(item.zone, item.liters)
                except Exception as e:
                    _LOGGER.error(
                        "Queue runner: start_liters(%s, %.2f) failed: %s",
                        item.zone, item.liters, e,
                    )
                    self._queue.popleft()
                    continue

                # Notify dashboard listeners that the queue advanced.
                self.mgr._notify_global()

                # Wait up to RUN_START_TIMEOUT for the device to ack ON.
                start_deadline = time.monotonic() + SCHEDULE_RUN_START_TIMEOUT_SECONDS
                while time.monotonic() < start_deadline and not v.session_active:
                    await asyncio.sleep(SCHEDULE_QUEUE_POLL_SECONDS)

                if not v.session_active:
                    _LOGGER.warning(
                        "Queue runner: %s never reported ON within %ds, advancing",
                        item.zone, SCHEDULE_RUN_START_TIMEOUT_SECONDS,
                    )
                    self._queue.popleft()
                    continue

                # Wait for it to finish naturally (device hardware target +
                # software guardrails will close it).
                while v.session_active:
                    if self.mgr.panic.active or not self.mgr.master_enable:
                        _LOGGER.warning(
                            "Queue runner: gate flipped during %s, leaving session "
                            "to existing failsafes and dropping queue",
                            item.zone,
                        )
                        self._queue.clear()
                        break
                    await asyncio.sleep(SCHEDULE_QUEUE_POLL_SECONDS)

                # Done with this zone (either completed normally or we
                # broke out due to a gate flip). Advance.
                self._queue.popleft()
                self.mgr._notify_global()

                if self._queue:
                    await asyncio.sleep(SCHEDULE_INTER_ZONE_GAP_SECONDS)

            _LOGGER.debug("Queue runner: queue drained, exiting")
        except asyncio.CancelledError:
            _LOGGER.info("Queue runner cancelled")
            raise
        except Exception as e:
            _LOGGER.error("Queue runner crashed: %s", e, exc_info=True)
        finally:
            self._runner_task = None
            self.mgr._notify_global()

    # ─────────────────────────────────────────────────────────────────────
    # Sensor helpers — next_run summary
    # ─────────────────────────────────────────────────────────────────────

    def compute_next_run_summary(self) -> dict:
        """Find the soonest enabled schedule's next firing across all schedules.

        Looks 8 days ahead (covers any weekday combination). Returns a
        dict that the NextRunSummary sensor flattens into its state +
        attributes.
        """
        try:
            schedules = self.store.all_schedules_typed()
        except Exception:
            schedules = []

        local_now = self._local_now()
        best_dt: Optional[datetime] = None
        best: Optional[Schedule] = None

        for sch in schedules:
            if not sch.enabled:
                continue
            for day_offset in range(8):
                check_date = local_now.date() + timedelta(days=day_offset)
                weekday_token = DAYS_OF_WEEK[check_date.weekday()]
                if sch.days and weekday_token not in sch.days:
                    continue
                # v4.0-rc-3 (F-B): unified resolver handles HH:MM and
                # sun-relative formats. For sun-relative on future
                # dates, this approximates by reusing today's sunrise/
                # sunset minute — close enough; the per-minute tick
                # catches the actual fire on the day.
                dt = self._resolve_schedule_datetime(sch, check_date)
                if dt is None:
                    continue
                if dt <= local_now:
                    continue
                if best_dt is None or dt < best_dt:
                    best_dt = dt
                    best = sch
                break  # earliest matching day for this schedule

        if best is None or best_dt is None:
            return {
                "state": "no_schedule",
                "next_run_at": None,
                "schedule_id": None,
                "schedule_name": None,
                "mode": None,
                "zones": [],
                "estimated_total_liters": None,
            }

        # Estimate liters for smart mode using current calc cache.
        est_total = None
        zones_preview: List[str] = list(best.zones)
        if best.mode == SCHEDULE_MODE_SMART and self.mgr.today_calculation is not None:
            wanted = set(best.zones) if best.zones else None
            est = 0.0
            zs: List[str] = []
            for zc in self.mgr.today_calculation.zones:
                if zc.skipped:
                    continue
                if wanted is not None and zc.zone not in wanted:
                    continue
                est += zc.liters
                zs.append(zc.zone)
            est_total = round(est, 2)
            zones_preview = zs
        elif best.mode == SCHEDULE_MODE_FIXED and best.fixed_liters_per_zone:
            est_total = round(best.fixed_liters_per_zone * len(best.zones), 2)

        return {
            "state": best_dt.isoformat(),
            "next_run_at": best_dt.isoformat(),
            "schedule_id": best.id,
            "schedule_name": best.name,
            "mode": best.mode,
            "zones": zones_preview,
            "estimated_total_liters": est_total,
        }
