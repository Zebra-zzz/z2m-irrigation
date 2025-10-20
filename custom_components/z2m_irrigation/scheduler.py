"""Irrigation scheduling manager."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change, async_call_later
from homeassistant.util import dt as dt_util

from .history import SessionHistory

_LOGGER = logging.getLogger(__name__)


class IrrigationScheduler:
    """Manages irrigation schedules and executes them."""

    def __init__(self, hass: HomeAssistant, history: SessionHistory, valve_manager) -> None:
        self.hass = hass
        self.history = history
        self.valve_manager = valve_manager
        self._schedules: Dict[str, Dict[str, Any]] = {}
        self._running_schedules: Dict[str, str] = {}  # schedule_id -> session_id
        self._unsubs = []
        self._schedule_check_task = None

    async def async_start(self) -> None:
        """Start the scheduler."""
        _LOGGER.info("Starting irrigation scheduler")
        await self._load_schedules()

        # Check for due schedules every minute
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                self._check_schedules,
                second=0
            )
        )

        # Initial check
        await self._check_schedules(dt_util.now())

    async def async_stop(self) -> None:
        """Stop the scheduler."""
        _LOGGER.info("Stopping irrigation scheduler")
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

        if self._schedule_check_task:
            self._schedule_check_task.cancel()

    async def _load_schedules(self) -> None:
        """Load all enabled schedules from database."""
        try:
            result = await self.history.supabase.table("irrigation_schedules").select("*").eq("enabled", True).execute()

            if result.data:
                for schedule in result.data:
                    self._schedules[schedule["id"]] = schedule
                    await self._calculate_next_run(schedule["id"])

                _LOGGER.info("Loaded %d enabled schedules", len(result.data))
        except Exception as e:
            _LOGGER.error("Failed to load schedules: %s", e)

    async def _calculate_next_run(self, schedule_id: str) -> None:
        """Calculate and update next run time for a schedule."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return

        now = dt_util.now()
        next_run = None

        if schedule["schedule_type"] == "time_based":
            next_run = self._calculate_time_based_next_run(schedule, now)
        elif schedule["schedule_type"] == "interval":
            next_run = self._calculate_interval_next_run(schedule, now)

        if next_run:
            # Update in memory
            schedule["next_run_at"] = next_run.isoformat()

            # Update in database
            try:
                await self.history.supabase.table("irrigation_schedules").update({
                    "next_run_at": next_run.isoformat()
                }).eq("id", schedule_id).execute()
            except Exception as e:
                _LOGGER.error("Failed to update next_run_at for schedule %s: %s", schedule_id, e)

    def _calculate_time_based_next_run(self, schedule: Dict[str, Any], now: datetime) -> Optional[datetime]:
        """Calculate next run time for time-based schedule."""
        times = schedule.get("times", [])
        days_of_week = schedule.get("days_of_week")  # None = every day, [0-6] = specific days

        if not times:
            return None

        # Get timezone
        tz = ZoneInfo(self.hass.config.time_zone)
        now_local = now.astimezone(tz)

        # Try today first, then next 7 days
        for day_offset in range(8):
            check_date = now_local.date() + timedelta(days=day_offset)
            check_weekday = check_date.weekday()  # 0=Monday, 6=Sunday

            # Check if this day is allowed
            if days_of_week is not None and check_weekday not in days_of_week:
                continue

            # Check all times for this day
            for time_str in times:
                try:
                    hour, minute = map(int, time_str.split(":"))
                    check_time = datetime.combine(check_date, time(hour, minute))
                    check_datetime = check_time.replace(tzinfo=tz)

                    # If this time is in the future, use it
                    if check_datetime > now_local:
                        return check_datetime
                except Exception as e:
                    _LOGGER.warning("Invalid time format '%s' in schedule: %s", time_str, e)

        return None

    def _calculate_interval_next_run(self, schedule: Dict[str, Any], now: datetime) -> Optional[datetime]:
        """Calculate next run time for interval-based schedule."""
        interval_hours = schedule.get("interval_hours")
        last_run_at = schedule.get("last_run_at")

        if not interval_hours:
            return None

        if last_run_at:
            # Parse last run time
            try:
                last_run = dt_util.parse_datetime(last_run_at)
                if last_run:
                    next_run = last_run + timedelta(hours=interval_hours)
                    if next_run > now:
                        return next_run
            except Exception:
                pass

        # No last run or it's overdue - schedule for now + interval
        return now + timedelta(hours=interval_hours)

    @callback
    async def _check_schedules(self, now: datetime) -> None:
        """Check if any schedules are due to run."""
        for schedule_id, schedule in list(self._schedules.items()):
            if not schedule.get("enabled", True):
                continue

            # Check if already running
            if schedule_id in self._running_schedules:
                continue

            # Check if due
            next_run_str = schedule.get("next_run_at")
            if not next_run_str:
                continue

            try:
                next_run = dt_util.parse_datetime(next_run_str)
                if next_run and now >= next_run:
                    # Schedule is due!
                    self.hass.async_create_task(self._execute_schedule(schedule_id))
            except Exception as e:
                _LOGGER.error("Error parsing next_run_at for schedule %s: %s", schedule_id, e)

    async def _execute_schedule(self, schedule_id: str) -> None:
        """Execute a scheduled irrigation run."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return

        _LOGGER.info("Executing schedule '%s' for valve '%s'", schedule["name"], schedule["valve_topic"])

        # Check conditions
        should_skip, skip_reason = await self._check_conditions(schedule)
        if should_skip:
            _LOGGER.info("Skipping schedule '%s': %s", schedule["name"], skip_reason)
            await self._log_schedule_run(schedule_id, None, "skipped", skip_reason)
            await self._update_last_run(schedule_id)
            await self._calculate_next_run(schedule_id)
            return

        # Create schedule run record
        try:
            result = await self.history.supabase.table("schedule_runs").insert({
                "schedule_id": schedule_id,
                "status": "running"
            }).execute()

            if result.data:
                run_id = result.data[0]["id"]
            else:
                run_id = None
        except Exception as e:
            _LOGGER.error("Failed to create schedule run record: %s", e)
            run_id = None

        # Start the valve
        try:
            valve_topic = schedule["valve_topic"]
            run_type = schedule["run_type"]
            run_value = schedule["run_value"]

            if run_type == "duration":
                self.valve_manager.start_timed(valve_topic, run_value)
            elif run_type == "volume":
                self.valve_manager.start_liters(valve_topic, run_value)

            # Track as running
            self._running_schedules[schedule_id] = run_id

            # Schedule completion check
            check_interval = 10  # Check every 10 seconds
            async_call_later(
                self.hass,
                check_interval,
                lambda _: self.hass.async_create_task(
                    self._check_schedule_completion(schedule_id, run_id)
                )
            )

        except Exception as e:
            _LOGGER.error("Failed to start valve for schedule '%s': %s", schedule["name"], e)
            if run_id:
                await self._log_schedule_run(schedule_id, run_id, "failed", str(e))

        # Update last run time
        await self._update_last_run(schedule_id)

        # Calculate next run
        await self._calculate_next_run(schedule_id)

    async def _check_schedule_completion(self, schedule_id: str, run_id: str) -> None:
        """Check if a scheduled run has completed."""
        if schedule_id not in self._running_schedules:
            return

        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return

        valve_topic = schedule["valve_topic"]
        valve = self.valve_manager.valves.get(valve_topic)

        if not valve or valve.state == "OFF":
            # Valve is off, run completed
            _LOGGER.info("Schedule '%s' completed", schedule["name"])

            # Update run record
            if run_id:
                await self._log_schedule_run(
                    schedule_id,
                    run_id,
                    "completed",
                    None,
                    valve.session_liters if valve else None,
                    valve.total_minutes if valve else None
                )

            # Remove from running
            self._running_schedules.pop(schedule_id, None)
        else:
            # Still running, check again later
            async_call_later(
                self.hass,
                10,
                lambda _: self.hass.async_create_task(
                    self._check_schedule_completion(schedule_id, run_id)
                )
            )

    async def _check_conditions(self, schedule: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Check if schedule conditions allow running."""
        conditions = schedule.get("conditions", {})

        if not conditions:
            return False, None

        # Check weather conditions
        if conditions.get("skip_if_rain"):
            # Check if it rained recently (would need weather integration)
            # TODO: Implement weather check
            pass

        if "min_temp" in conditions or "max_temp" in conditions:
            # Check temperature (would need weather integration)
            # TODO: Implement temperature check
            pass

        # Check soil moisture sensor
        if "soil_moisture_entity" in conditions:
            entity_id = conditions["soil_moisture_entity"]
            max_moisture = conditions.get("max_moisture", 50)

            state = self.hass.states.get(entity_id)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    moisture = float(state.state)
                    if moisture >= max_moisture:
                        return True, f"Soil moisture {moisture}% >= {max_moisture}%"
                except ValueError:
                    pass

        return False, None

    async def _update_last_run(self, schedule_id: str) -> None:
        """Update last run timestamp."""
        now = dt_util.now()

        # Update in memory
        if schedule_id in self._schedules:
            self._schedules[schedule_id]["last_run_at"] = now.isoformat()

        # Update in database
        try:
            await self.history.supabase.table("irrigation_schedules").update({
                "last_run_at": now.isoformat()
            }).eq("id", schedule_id).execute()
        except Exception as e:
            _LOGGER.error("Failed to update last_run_at: %s", e)

    async def _log_schedule_run(
        self,
        schedule_id: str,
        run_id: Optional[str],
        status: str,
        skip_reason: Optional[str] = None,
        actual_volume: Optional[float] = None,
        actual_duration: Optional[float] = None
    ) -> None:
        """Log schedule run completion."""
        try:
            if run_id:
                # Update existing run record
                await self.history.supabase.table("schedule_runs").update({
                    "completed_at": dt_util.now().isoformat(),
                    "status": status,
                    "skip_reason": skip_reason,
                    "actual_volume": actual_volume,
                    "actual_duration": actual_duration
                }).eq("id", run_id).execute()
            else:
                # Create new run record (for skipped runs)
                await self.history.supabase.table("schedule_runs").insert({
                    "schedule_id": schedule_id,
                    "status": status,
                    "skip_reason": skip_reason,
                    "completed_at": dt_util.now().isoformat()
                }).execute()
        except Exception as e:
            _LOGGER.error("Failed to log schedule run: %s", e)

    async def reload_schedules(self) -> None:
        """Reload schedules from database."""
        _LOGGER.info("Reloading schedules")
        self._schedules.clear()
        await self._load_schedules()

    async def add_schedule(self, schedule_data: Dict[str, Any]) -> str:
        """Add a new schedule."""
        try:
            result = await self.history.supabase.table("irrigation_schedules").insert(schedule_data).execute()

            if result.data:
                schedule_id = result.data[0]["id"]
                self._schedules[schedule_id] = result.data[0]
                await self._calculate_next_run(schedule_id)
                _LOGGER.info("Added schedule '%s' (ID: %s)", schedule_data.get("name"), schedule_id)
                return schedule_id
        except Exception as e:
            _LOGGER.error("Failed to add schedule: %s", e)
            raise

    async def update_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> None:
        """Update an existing schedule."""
        try:
            await self.history.supabase.table("irrigation_schedules").update(schedule_data).eq("id", schedule_id).execute()

            # Reload from database
            result = await self.history.supabase.table("irrigation_schedules").select("*").eq("id", schedule_id).execute()
            if result.data:
                self._schedules[schedule_id] = result.data[0]
                await self._calculate_next_run(schedule_id)
                _LOGGER.info("Updated schedule ID: %s", schedule_id)
        except Exception as e:
            _LOGGER.error("Failed to update schedule: %s", e)
            raise

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule."""
        try:
            await self.history.supabase.table("irrigation_schedules").delete().eq("id", schedule_id).execute()
            self._schedules.pop(schedule_id, None)
            self._running_schedules.pop(schedule_id, None)
            _LOGGER.info("Deleted schedule ID: %s", schedule_id)
        except Exception as e:
            _LOGGER.error("Failed to delete schedule: %s", e)
            raise

    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get a schedule by ID."""
        return self._schedules.get(schedule_id)

    def get_all_schedules(self) -> Dict[str, Dict[str, Any]]:
        """Get all schedules."""
        return self._schedules.copy()
