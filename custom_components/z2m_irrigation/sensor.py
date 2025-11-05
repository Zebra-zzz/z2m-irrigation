from __future__ import annotations
from datetime import datetime, timezone
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .manager import ValveManager, Valve
from .const import DOMAIN, MANUFACTURER, MODEL, SIG_NEW_VALVE, sig_update

async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]["manager"]
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
        ], True)
    for v in list(mgr.valves.values()):
        _add_for(v)
    entry.async_on_unload(async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_for))

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
