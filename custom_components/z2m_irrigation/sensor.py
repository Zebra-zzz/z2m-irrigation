from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .manager import ValveManager, Valve
from .const import (
    DOMAIN, MANUFACTURER, MODEL,
    SIG_NEW_VALVE, sig_update,
    SIG_GLOBAL_UPDATE, sig_zone_config_changed,
)
from .zone_store import ZoneConfig

async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]["manager"]

    # v3.x — per-valve sensors. New per-zone v4.0 sensors are added here too
    # so they appear under the same device card as the existing valve sensors.
    @callback
    def _add_for(v: Valve):
        async_add_entities([
            FlowLpm(mgr, v),
            SessionUsed(mgr, v),
            SessionDuration(mgr, v),
            TotalLiters(mgr, v),
            TotalMinutes(mgr, v),
            LifetimeTotalLiters(mgr, v),
            LifetimeTotalMinutes(mgr, v),
            LifetimeSessionCount(mgr, v),
            Last24hLiters(mgr, v),
            Last24hMinutes(mgr, v),
            Last7dLiters(mgr, v),
            Last7dMinutes(mgr, v),
            LastSessionStart(mgr, v),
            LastSessionEnd(mgr, v),
            SessionRemainingTime(mgr, v),
            SessionRemainingLiters(mgr, v),
            SessionCount(mgr, v),
            BatteryLevel(mgr, v),
            LinkQuality(mgr, v),
            # v4.0-alpha-1 — per-zone config sensors
            ZoneFactorSensor(mgr, v),
            ZoneLPerMmSensor(mgr, v),
            ZoneBaseMmSensor(mgr, v),
            # v4.0-alpha-3 — per-zone history-derived sensors
            ZoneAvgFlow7dSensor(mgr, v),
            ZoneLastRunLitersSensor(mgr, v),
            ZoneLastRunAtSensor(mgr, v),
            # v4.0-alpha-4 — per-zone daily delivery time-series
            ZoneDailyHistorySensor(mgr, v),
        ], True)
    for v in list(mgr.valves.values()):
        _add_for(v)
    entry.async_on_unload(async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_for))

    # v4.0-alpha-1 — global integration-level sensors. Singletons that are
    # not tied to any one valve. Added once per config entry.
    async_add_entities([
        TodayCalculationSensor(mgr),
        ActiveSessionSummarySensor(mgr),
        WeekSummarySensor(mgr),
        NextRunSummarySensor(mgr),
        SchedulesSensor(mgr),
        # v4.0-alpha-3 — global schedule timeline
        ScheduleHistorySensor(mgr),
        # v4.0-alpha-4 — global daily delivery totals
        DailyTotalsSensor(mgr),
    ], True)

class BaseValveSensor(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, mgr: ValveManager, valve: Valve, name: str, unit: str | None, state_class: str | None):
        self.mgr = mgr; self.valve = valve
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._sig = sig_update(valve.topic); self._unsub = None
    @property
    def unique_id(self) -> str:
        base = f"{self.valve.topic}_{self.name}".lower().replace(" ", "_")
        return base
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.valve.topic)}, manufacturer=MANUFACTURER, model=MODEL, name=self.valve.name)
    async def async_added_to_hass(self) -> None:
        @callback
        def _cb():
            self.async_write_ha_state()
        self._unsub = async_dispatcher_connect(self.hass, self._sig, _cb)
        # push an initial state so the entity shows immediately
        self.async_write_ha_state()
    async def async_will_remove_from_hass(self) -> None:
        if self._unsub: self._unsub(); self._unsub = None

class FlowLpm(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Flow", "L/min", "measurement")
    @property
    def native_value(self): return round(self.valve.flow_lpm, 3)

class SessionUsed(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Session Used", "L", "measurement")
    @property
    def native_value(self): return round(self.valve.session_liters, 2)

class TotalLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Total", "L", "total_increasing")
    @property
    def native_value(self): return round(self.valve.total_liters, 2)

class TotalMinutes(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Total Minutes", "min", "total_increasing")
    @property
    def native_value(self): return round(self.valve.total_minutes, 2)

class SessionDuration(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Session Duration", "min", "measurement")
    @property
    def native_value(self):
        import time
        if not self.valve.session_active:
            return 0
        elapsed_s = time.monotonic() - self.valve.session_start_ts
        return round(elapsed_s / 60.0, 2)

class SessionRemainingTime(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Remaining Time", "min", "measurement")
    @property
    def native_value(self):
        import time
        if not self.valve.session_active:
            return None
        # If timed run, show actual remaining time
        if self.valve.session_end_ts is not None:
            remaining_s = max(0.0, self.valve.session_end_ts - time.monotonic())
            return round(remaining_s / 60.0, 2)
        # If volume run with flow, estimate time
        if self.valve.target_liters and self.valve.flow_lpm > 0:
            remaining_liters = max(0, self.valve.target_liters - self.valve.session_liters)
            estimated_min = remaining_liters / self.valve.flow_lpm
            return round(estimated_min, 2)
        # Manual operation - infinite
        return None

class SessionRemainingLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Remaining Liters", "L", "measurement")
    @property
    def native_value(self):
        import time
        if not self.valve.session_active:
            return None
        # If volume run, show actual remaining liters
        if self.valve.target_liters is not None:
            remaining = max(0, self.valve.target_liters - self.valve.session_liters)
            return round(remaining, 2)
        # If timed run with flow, estimate liters
        if self.valve.session_end_ts and self.valve.flow_lpm > 0:
            remaining_s = max(0.0, self.valve.session_end_ts - time.monotonic())
            estimated_liters = (remaining_s / 60.0) * self.valve.flow_lpm
            return round(estimated_liters, 2)
        # Manual operation
        return None

class SessionCount(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Session Count", None, "total")
    @property
    def native_value(self): return self.valve.session_count

class BatteryLevel(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Battery", "%", None)
        self._attr_device_class = "battery"
    @property
    def native_value(self): return self.valve.battery

class LinkQuality(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Link Quality", None, None)
    @property
    def native_value(self): return self.valve.link_quality

class LifetimeTotalLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Lifetime Total", "L", "total_increasing")
    @property
    def native_value(self): return round(self.valve.lifetime_total_liters, 2)

class LifetimeTotalMinutes(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Lifetime Total Minutes", "min", "total_increasing")
    @property
    def native_value(self): return round(self.valve.lifetime_total_minutes, 2)

class LifetimeSessionCount(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Lifetime Session Count", None, "total")
    @property
    def native_value(self): return self.valve.lifetime_session_count

class Last24hLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last 24h", "L", "total")
    @property
    def native_value(self): return round(self.valve.last_24h_liters, 2)

class Last24hMinutes(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last 24h Minutes", "min", "total")
    @property
    def native_value(self): return round(self.valve.last_24h_minutes, 2)

class Last7dLiters(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last 7 Days", "L", "total")
    @property
    def native_value(self): return round(self.valve.last_7d_liters, 2)

class Last7dMinutes(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last 7 Days Minutes", "min", "total")
    @property
    def native_value(self): return round(self.valve.last_7d_minutes, 2)

class LastSessionStart(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last Session Start", None, None)
    @property
    def device_class(self): return "timestamp"
    @property
    def native_value(self):
        if not self.valve.last_session_start:
            return None
        try:
            # Parse ISO string to datetime object with UTC timezone
            dt = datetime.fromisoformat(self.valve.last_session_start.replace('Z', '+00:00'))
            # Ensure timezone is set (Home Assistant requires timezone-aware datetime)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            return None

class LastSessionEnd(BaseValveSensor):
    def __init__(self, mgr: ValveManager, valve: Valve): super().__init__(mgr, valve, "Last Session End", None, None)
    @property
    def device_class(self): return "timestamp"
    @property
    def native_value(self):
        if not self.valve.last_session_end:
            return None
        try:
            # Parse ISO string to datetime object with UTC timezone
            dt = datetime.fromisoformat(self.valve.last_session_end.replace('Z', '+00:00'))
            # Ensure timezone is set (Home Assistant requires timezone-aware datetime)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-1 — Per-zone config sensors
#
# Surface the ZoneStore values as sensors so the dashboard can render and
# automations can read them. Each subscribes to two signals:
#   - sig_update(topic) for valve-state-driven UI refreshes (cheap)
#   - sig_zone_config_changed(topic) for config edits via the new services
# ─────────────────────────────────────────────────────────────────────────────


class BaseZoneConfigSensor(BaseValveSensor):
    """Base for sensors backed by `ZoneStore.get_zone(topic)`."""

    def __init__(self, mgr: ValveManager, valve: Valve, name: str, unit: Optional[str]):
        super().__init__(mgr, valve, name, unit, None)
        self._unsub_cfg = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _on_cfg():
            self.async_write_ha_state()

        self._unsub_cfg = async_dispatcher_connect(
            self.hass, sig_zone_config_changed(self.valve.topic), _on_cfg,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub_cfg:
            self._unsub_cfg()
            self._unsub_cfg = None

    def _zone_cfg(self) -> ZoneConfig:
        if self.mgr.zone_store is None:
            return ZoneConfig()
        return self.mgr.zone_store.get_zone(self.valve.topic)


class ZoneFactorSensor(BaseZoneConfigSensor):
    """Per-zone calculator multiplier (default 1.0).

    Edited via `z2m_irrigation.set_zone_factor`. The dashboard's "Setup"
    tab will surface this as an editable slider in alpha-4.
    """
    _attr_icon = "mdi:tune-variant"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Zone Factor", None)

    @property
    def native_value(self) -> float:
        return self._zone_cfg().factor


class ZoneLPerMmSensor(BaseZoneConfigSensor):
    """Per-zone calibration: liters delivered per 1 mm of irrigation depth."""
    _attr_icon = "mdi:water-percent"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Zone L per mm", "L/mm")

    @property
    def native_value(self) -> float:
        return self._zone_cfg().l_per_mm


class ZoneBaseMmSensor(BaseZoneConfigSensor):
    """Per-zone baseline daily water depth (mm) — calculator input."""
    _attr_icon = "mdi:waves-arrow-up"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Zone Base mm", "mm")

    @property
    def native_value(self) -> float:
        return self._zone_cfg().base_mm


# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-3 — Per-zone history-derived sensors
#
# Source the underlying numbers from the existing SQLite session history
# (via fields the manager refreshes onto the Valve object on every 15-min
# tick AND on every session end). The sensors themselves are pure
# rendering — no I/O.
# ─────────────────────────────────────────────────────────────────────────────


class ZoneAvgFlow7dSensor(BaseValveSensor):
    """Rolling average flow rate (L/min) over the most recent N completed
    sessions for this zone.

    Used by:
      * The Insight tab — to spot a degrading flow rate (clogged filter,
        valve wear, pressure drop).
      * The ETA estimate on the Hero card's Running state.

    Refreshed by the manager's existing 15-min `_periodic_refresh_time_metrics`
    loop AND on every session end via the `_end_and_sync` path. Reports
    `None` (→ HA `unknown`) if there's no completed-session history yet.
    """
    _attr_icon = "mdi:chart-line"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Avg Flow 7d", "L/min", "measurement")

    @property
    def native_value(self):
        if self.valve.avg_flow_lpm_7d is None:
            return None
        return round(self.valve.avg_flow_lpm_7d, 3)


class ZoneLastRunLitersSensor(BaseValveSensor):
    """Volume delivered in the most recent completed session (L).

    Distinct from `Last Session End` (timestamp) and from `Last 24h` /
    `Last 7 Days` (windowed sums) — this is the single-event delivery
    that the dashboard's per-zone tile shows under "last run: X L".
    """
    _attr_icon = "mdi:water-check"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Last Run Liters", "L", "measurement")

    @property
    def native_value(self):
        return self.valve.last_session_liters


class ZoneLastRunAtSensor(BaseValveSensor):
    """Wall-clock timestamp of the most recent session END.

    Mirrors `LastSessionEnd` from v3.x for consistency with the new
    naming scheme. Backed by the same `valve.last_session_end` field
    that v3.x already maintains, so no extra DB hits — just an alias
    sensor with a more dashboard-friendly name.
    """

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Last Run At", None, None)

    @property
    def device_class(self):
        return "timestamp"

    @property
    def native_value(self):
        if not self.valve.last_session_end:
            return None
        try:
            dt = datetime.fromisoformat(
                self.valve.last_session_end.replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            return None


class ZoneDailyHistorySensor(BaseValveSensor):
    """v4.0-alpha-4 — `sensor.<zone>_daily_history`.

    State = total liters delivered by this zone over the cached window
    (default 30 days). The `days` attribute carries the per-day series
    (most-recent first), with zero-filled gaps so the dashboard chart
    can render contiguous bars.

    Reads from the manager's pre-built `daily_summary` cache — no DB
    hits at render time. The cache is refreshed on the existing 15-min
    `_periodic_refresh_time_metrics` loop and on every session end, so
    the chart updates within seconds of a finished run.

    Subscribes to BOTH the per-valve `sig_update` channel (so the row
    refreshes on the same beat as the rest of the per-valve sensors)
    AND the global `SIG_GLOBAL_UPDATE` channel (so service-driven
    aggregation refreshes propagate without waiting for an MQTT msg).
    """
    _attr_icon = "mdi:chart-bar"
    _attr_native_unit_of_measurement = "L"

    def __init__(self, mgr: ValveManager, valve: Valve):
        super().__init__(mgr, valve, "Daily History", "L", "measurement")
        self._unsub_global = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _on_global():
            self.async_write_ha_state()

        self._unsub_global = async_dispatcher_connect(
            self.hass, SIG_GLOBAL_UPDATE, _on_global,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub_global:
            self._unsub_global()
            self._unsub_global = None

    def _series(self):
        """Return this valve's `ZoneSeries` from the cache, or None."""
        summary = self.mgr.daily_summary
        if summary is None:
            return None
        for zs in summary.zones:
            if zs.zone == self.valve.topic:
                return zs
        return None

    @property
    def native_value(self):
        zs = self._series()
        if zs is None:
            return None
        return zs.total_liters

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        zs = self._series()
        if zs is None:
            return {"available": False}
        return {
            "available": True,
            "days_back": (
                self.mgr.daily_summary.days_back
                if self.mgr.daily_summary is not None else 0
            ),
            "built_at": (
                self.mgr.daily_summary.built_at
                if self.mgr.daily_summary is not None else None
            ),
            "total_liters": zs.total_liters,
            "total_minutes": zs.total_minutes,
            "total_sessions": zs.total_sessions,
            "days": [
                {
                    "date": d.date,
                    "liters": d.liters,
                    "minutes": d.minutes,
                    "sessions": d.sessions,
                }
                for d in zs.days
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-1 — Global (integration-level) sensors
#
# These are singletons (one per config entry) and are NOT tied to any
# valve's device. They subscribe to SIG_GLOBAL_UPDATE which the manager
# fires whenever the calculator cache refreshes, master_enable toggles,
# or any zone config changes. Sensors that also need to react to per-valve
# state (active session, any-running) additionally subscribe to per-valve
# `sig_update` via the SIG_NEW_VALVE signal.
# ─────────────────────────────────────────────────────────────────────────────


class BaseGlobalSensor(SensorEntity):
    """Base class for integration-level singleton sensors."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, mgr: ValveManager, name: str, unique_id: str, unit: Optional[str] = None):
        self.mgr = mgr
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_unit_of_measurement = unit
        self._unsub_global = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_update():
            self.async_write_ha_state()

        self._unsub_global = async_dispatcher_connect(
            self.hass, SIG_GLOBAL_UPDATE, _on_update,
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_global:
            self._unsub_global()
            self._unsub_global = None


class _PerValveAwareGlobalSensor(BaseGlobalSensor):
    """Global sensor that *also* needs to redraw on per-valve updates.

    Subscribes to SIG_NEW_VALVE so it can wire up sig_update(topic) for
    every valve, both the ones present at startup and any that arrive
    later. Used by ActiveSessionSummary and any other "live mirror of
    valve state" sensors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._valve_unsubs: list = []
        self._unsub_new_valve = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _on_valve_update():
            self.async_write_ha_state()

        @callback
        def _wire_valve(v: Valve):
            self._valve_unsubs.append(
                async_dispatcher_connect(
                    self.hass, sig_update(v.topic), _on_valve_update,
                )
            )

        for v in list(self.mgr.valves.values()):
            _wire_valve(v)

        self._unsub_new_valve = async_dispatcher_connect(
            self.hass, SIG_NEW_VALVE, _wire_valve,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub_new_valve:
            self._unsub_new_valve()
            self._unsub_new_valve = None
        for unsub in self._valve_unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._valve_unsubs.clear()


class TodayCalculationSensor(BaseGlobalSensor):
    """Total liters the calculator says should be applied today.

    State = total liters across all runnable zones for the most recent
    calculator run. Attributes carry the per-zone breakdown plus the
    weather inputs that went into the calc, so the dashboard's
    Calculator card can render the entire reasoning in one place.

    Updated by:
      * ValveManager._periodic_recalculate_today (every 15 min)
      * ValveManager.recalculate_today() (on demand via service or zone
        config change)
    """
    _attr_icon = "mdi:calculator-variant-outline"
    _attr_native_unit_of_measurement = "L"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Today Calculation",
            "z2m_irrigation_today_calculation", "L",
        )

    @property
    def native_value(self):
        result = self.mgr.today_calculation
        if result is None:
            return None
        return result.total_liters

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        result = self.mgr.today_calculation
        if result is None:
            return {"status": "no_data"}
        return {
            "vpd_kpa": result.weather.vpd_kpa,
            "vpd_kpa_effective": result.weather.effective_vpd,
            "rain_today_mm": result.weather.rain_today_mm,
            "rain_today_mm_effective": result.weather.effective_rain_today,
            "rain_forecast_24h_mm": result.weather.fc24_mm,
            "rain_forecast_24h_mm_effective": result.weather.effective_fc24,
            "temperature_c": result.weather.temp_c,
            "dryness": result.dryness,
            "runnable_zones": result.runnable_zones,
            "total_zones": len(result.zones),
            "zones": [
                {
                    "zone": z.zone,
                    "base_mm": z.base_mm,
                    "factor": z.factor,
                    "l_per_mm": z.l_per_mm,
                    "need_mm": z.need_mm,
                    "liters": z.liters,
                    "skipped": z.skipped,
                    "skip_reason": z.skip_reason,
                }
                for z in result.zones
            ],
        }


class ActiveSessionSummarySensor(_PerValveAwareGlobalSensor):
    """Live mirror of any in-flight valve session.

    State = friendly name of the currently-running valve, or `idle`.
    If multiple valves are somehow running concurrently (manual control),
    state shows the first active one and the attribute `concurrent_valves`
    lists all of them.

    Powers the Hero card's "Running" state on the v4.0 dashboard.
    """
    _attr_icon = "mdi:water-pump"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Active Session",
            "z2m_irrigation_active_session_summary",
        )

    def _active_valves(self) -> list[Valve]:
        return [v for v in self.mgr.valves.values() if v.session_active]

    @property
    def native_value(self) -> str:
        active = self._active_valves()
        if not active:
            return "idle"
        return active[0].name

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        active = self._active_valves()
        if not active:
            return {"running": False}
        v = active[0]
        elapsed_s = max(0.0, time.monotonic() - v.session_start_ts) if v.session_start_ts else 0.0
        attrs: Dict[str, Any] = {
            "running": True,
            "valve": v.topic,
            "name": v.name,
            "trigger_type": v.trigger_type,
            "elapsed_seconds": round(elapsed_s, 1),
            "session_liters": round(v.session_liters, 2),
            "flow_lpm": round(v.flow_lpm, 3),
            "target_liters": v.target_liters,
            "shutoff_in_progress": v.shutoff_in_progress,
            "shutoff_reason": v.shutoff_reason or None,
        }
        # ETA in seconds for volume runs
        if v.target_liters and v.flow_lpm > 0 and not v.shutoff_in_progress:
            remaining_l = max(0.0, v.target_liters - v.session_liters)
            attrs["eta_seconds"] = round((remaining_l / v.flow_lpm) * 60.0, 1)
        # Concurrent active valves (rare; manual control only)
        if len(active) > 1:
            attrs["concurrent_valves"] = [vv.topic for vv in active]
        return attrs


class WeekSummarySensor(_PerValveAwareGlobalSensor):
    """Total liters delivered across all valves in the last 7 days.

    State = sum of `valve.last_7d_liters` across all known valves. The
    per-valve 7d aggregate is refreshed by `_periodic_refresh_time_metrics`
    every 15 min and after every session ends, so this sensor is always
    a reflection of the latest aggregate.
    """
    _attr_icon = "mdi:calendar-week"
    _attr_native_unit_of_measurement = "L"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Week Summary",
            "z2m_irrigation_week_summary", "L",
        )

    @property
    def native_value(self) -> float:
        return round(sum(v.last_7d_liters for v in self.mgr.valves.values()), 2)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "valves": [
                {
                    "valve": v.topic,
                    "name": v.name,
                    "last_7d_liters": round(v.last_7d_liters, 2),
                    "last_7d_minutes": round(v.last_7d_minutes, 2),
                    "last_24h_liters": round(v.last_24h_liters, 2),
                }
                for v in self.mgr.valves.values()
            ],
        }


class NextRunSummarySensor(BaseGlobalSensor):
    """v4.0-alpha-2 — `sensor.z2m_irrigation_next_run_summary`.

    State = ISO timestamp of the soonest enabled schedule's next firing,
    or `no_schedule` if there are none. Attributes carry the schedule
    metadata, mode, zone preview, and an estimated total liters (smart
    mode pulls from the calculator cache; fixed mode multiplies).

    Updated whenever the engine fires, schedules are mutated, the
    calculator refreshes, or the queue advances — all of which call
    `manager._notify_global()`, which fires SIG_GLOBAL_UPDATE.
    """
    _attr_icon = "mdi:clock-outline"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Next Run",
            "z2m_irrigation_next_run_summary",
        )

    def _summary(self) -> Dict[str, Any]:
        if self.mgr.schedule_engine is None:
            return {
                "state": "no_schedule",
                "next_run_at": None,
                "schedule_id": None,
                "schedule_name": None,
                "mode": None,
                "zones": [],
                "estimated_total_liters": None,
            }
        return self.mgr.schedule_engine.compute_next_run_summary()

    @property
    def native_value(self):
        s = self._summary()
        if s["state"] == "no_schedule":
            return "no_schedule"
        # Return ISO string; the dashboard formats it relatively.
        return s["state"]

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        s = self._summary()
        return {
            "next_run_at": s["next_run_at"],
            "schedule_id": s["schedule_id"],
            "schedule_name": s["schedule_name"],
            "mode": s["mode"],
            "zones": s["zones"],
            "estimated_total_liters": s["estimated_total_liters"],
            "skip_today": (
                self.mgr.schedule_engine.skip_today_active
                if self.mgr.schedule_engine is not None else False
            ),
            "master_enable": self.mgr.master_enable,
            "panic_active": self.mgr.panic.active,
            "queue": (
                self.mgr.schedule_engine.queue_snapshot()
                if self.mgr.schedule_engine is not None else []
            ),
        }


class SchedulesSensor(BaseGlobalSensor):
    """v4.0-alpha-2 — `sensor.z2m_irrigation_schedules`.

    State = count of enabled schedules. Attributes carry the full
    schedule list (id, name, time, days, mode, zones, last_run_at,
    last_run_outcome) for the dashboard's Schedule tab to render.
    """
    _attr_icon = "mdi:calendar-multiselect"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Schedules",
            "z2m_irrigation_schedules",
        )

    def _all(self) -> list:
        if self.mgr.zone_store is None:
            return []
        return self.mgr.zone_store.all_schedules()

    @property
    def native_value(self) -> int:
        return sum(1 for s in self._all() if s.get("enabled", True))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {
            "total": len(self._all()),
            "schedules": self._all(),
        }


class ScheduleHistorySensor(BaseGlobalSensor):
    """v4.0-alpha-3 — `sensor.z2m_irrigation_schedule_history`.

    State = count of recorded schedule events in the retention window
    (90 days by default, capped at HISTORY_MAX_ENTRIES). The `events`
    attribute carries the most recent N events (most recent first), each
    one a dict with `at`, `kind` (`fired`/`skipped`), `outcome`,
    `schedule_name`, `mode`, `trigger`, `zones`, `total_liters`.

    Powers the Insight tab's "what happened in the last 7 days" timeline.

    The sensor surfaces a clamped slice (most recent 100 events) in
    attributes to keep the recorder happy — the full retained set lives
    in the JSON store and can be read directly via the `zone_store` if
    something ever needs more than 100.
    """
    _attr_icon = "mdi:history"

    _ATTR_LIMIT = 100

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Schedule History",
            "z2m_irrigation_schedule_history",
        )

    def _all_events(self) -> list:
        if self.mgr.zone_store is None:
            return []
        return self.mgr.zone_store.schedule_events()

    @property
    def native_value(self) -> int:
        return len(self._all_events())

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        if self.mgr.zone_store is None:
            return {"events": [], "total": 0}
        events = self.mgr.zone_store.schedule_events(limit=self._ATTR_LIMIT)
        return {
            "events": events,
            "total": len(self._all_events()),
            "shown": len(events),
        }


class DailyTotalsSensor(BaseGlobalSensor):
    """v4.0-alpha-4 — `sensor.z2m_irrigation_daily_totals`.

    State = total liters delivered across all zones over the cached
    window (default 30 days). The `days` attribute carries the
    combined-across-zones daily series (most-recent first), and the
    `zones` attribute carries the per-zone totals over the same window.

    The dashboard's Insight tab uses this for the "all zones" stacked
    bar chart at the top of the page; per-zone breakdowns come from
    the per-zone `daily_history` sensors.

    Reads the manager's `daily_summary` cache — no DB hits at render
    time. Cache is refreshed on the existing 15-min loop and on every
    session end (see `manager.refresh_daily_summary`).
    """
    _attr_icon = "mdi:chart-bar-stacked"
    _attr_native_unit_of_measurement = "L"

    def __init__(self, mgr: ValveManager):
        super().__init__(
            mgr, "Z2M Irrigation Daily Totals",
            "z2m_irrigation_daily_totals", "L",
        )

    @property
    def native_value(self):
        summary = self.mgr.daily_summary
        if summary is None:
            return None
        return round(sum(d.liters for d in summary.combined), 2)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        summary = self.mgr.daily_summary
        if summary is None:
            return {"available": False}
        return {
            "available": True,
            "days_back": summary.days_back,
            "built_at": summary.built_at,
            "total_liters": round(sum(d.liters for d in summary.combined), 2),
            "total_minutes": round(sum(d.minutes for d in summary.combined), 2),
            "total_sessions": sum(d.sessions for d in summary.combined),
            "days": [
                {
                    "date": d.date,
                    "liters": d.liters,
                    "minutes": d.minutes,
                    "sessions": d.sessions,
                }
                for d in summary.combined
            ],
            "zones": [
                {
                    "zone": z.zone,
                    "name": z.name,
                    "total_liters": z.total_liters,
                    "total_minutes": z.total_minutes,
                    "total_sessions": z.total_sessions,
                }
                for z in summary.zones
            ],
        }
