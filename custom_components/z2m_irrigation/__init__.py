"""Z2M Irrigation (Sonoff Valves) integration."""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_VALVES,
    CONF_VALVE_NAME,
    CONF_VALVE_TOPIC,
    CONF_FLOW_UNIT,
    CONF_MAX_RUNTIME,
    CONF_NOISE_FLOOR,
    FLOW_UNIT_M3H,
    FLOW_UNIT_LPM,
    SERVICE_START_TIMED,
    SERVICE_START_LITRES,
    SERVICE_STOP,
    SERVICE_RESET_TOTAL,
    ATTR_NAME,
    ATTR_MINUTES,
    ATTR_LITRES,
    ATTR_HARD_TIMEOUT_MIN,
    SIGNAL_VALVE_UPDATE,
    EVENT_SESSION_STARTED,
    EVENT_SESSION_ENDED,
    MODE_TIMED,
    MODE_LITRES,
    MODE_MANUAL,
    END_REASON_AUTO_OFF,
    END_REASON_LITRES_REACHED,
    END_REASON_MANUAL,
    END_REASON_FAILSAFE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

STORAGE_VERSION = 1
STORAGE_KEY_TOTALS = f"{DOMAIN}_totals"
STORAGE_KEY_SESSIONS = f"{DOMAIN}_sessions"


class ValveManager:
    """Manage valve state, flow integration, and session logging."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.config_entry = config_entry
        self.valves: dict[str, dict[str, Any]] = {}
        self.mqtt_subscriptions = []
        self._totals_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_TOTALS)
        self._sessions_store = Store(hass, STORAGE_VERSION, STORAGE_KEY_SESSIONS)
        self._totals: dict[str, float] = {}
        self._sessions: list[dict[str, Any]] = []

    async def async_setup(self):
        """Set up the valve manager."""
        await self._load_totals()
        await self._load_sessions()

        valves_config = self.config_entry.options.get(
            CONF_VALVES, self.config_entry.data.get(CONF_VALVES, [])
        )

        for valve_config in valves_config:
            valve_name = valve_config[CONF_VALVE_NAME]
            self.valves[valve_name] = {
                "config": valve_config,
                "state": "OFF",
                "flow_raw": 0.0,
                "flow_lpm": 0.0,
                "battery": None,
                "linkquality": None,
                "last_update": None,
                "session_start": None,
                "session_used_l": 0.0,
                "auto_off_timer": None,
                "mode": None,
                "target": None,
            }

            topic = valve_config[CONF_VALVE_TOPIC]
            unsub = await mqtt.async_subscribe(
                self.hass, topic, self._make_mqtt_callback(valve_name), qos=1
            )
            self.mqtt_subscriptions.append(unsub)

        return True

    async def async_unload(self):
        """Unload the valve manager."""
        for unsub in self.mqtt_subscriptions:
            unsub()

        for valve_name in self.valves:
            if self.valves[valve_name]["auto_off_timer"]:
                self.valves[valve_name]["auto_off_timer"]()

    def _make_mqtt_callback(self, valve_name: str):
        @callback
        def mqtt_message_received(msg):
            try:
                payload = json.loads(msg.payload)
            except json.JSONDecodeError:
                _LOGGER.warning(f"Invalid JSON from {msg.topic}: {msg.payload}")
                return

            valve = self.valves.get(valve_name)
            if not valve:
                return

            now = datetime.utcnow()
            valve["last_update"] = now

            if "state" in payload:
                valve["state"] = payload["state"]

            if "flow" in payload:
                valve["flow_raw"] = float(payload["flow"])
                flow_lpm = self._convert_to_lpm(valve_name, valve["flow_raw"])
                valve["flow_lpm"] = flow_lpm

                if valve["state"] == "ON" and valve["session_start"]:
                    dt_seconds = 10
                    if "last_flow_time" in valve:
                        dt_seconds = (now - valve["last_flow_time"]).total_seconds()
                    valve["last_flow_time"] = now

                    litres = flow_lpm * dt_seconds / 60.0
                    valve["session_used_l"] += litres
                    self._totals[valve_name] = self._totals.get(valve_name, 0) + litres

                    if valve["mode"] == MODE_LITRES and valve["target"]:
                        target_litres = valve["target"]["litres"]
                        if valve["session_used_l"] >= target_litres:
                            self.hass.async_create_task(
                                self._stop_valve(valve_name, END_REASON_LITRES_REACHED)
                            )

            if "battery" in payload:
                valve["battery"] = payload["battery"]

            if "linkquality" in payload:
                valve["linkquality"] = payload["linkquality"]

            async_dispatcher_send(self.hass, SIGNAL_VALVE_UPDATE.format(valve_name))

        return mqtt_message_received

    def _convert_to_lpm(self, valve_name: str, flow_raw: float) -> float:
        """Convert flow to L/min and apply noise floor."""
        valve = self.valves[valve_name]
        config = valve["config"]
        flow_unit = config.get(CONF_FLOW_UNIT, FLOW_UNIT_LPM)
        noise_floor = config.get(CONF_NOISE_FLOOR, 0.3)

        if flow_unit == FLOW_UNIT_M3H:
            flow_lpm = flow_raw * 1000.0 / 60.0
        else:
            flow_lpm = flow_raw

        if flow_lpm < noise_floor:
            flow_lpm = 0.0

        return flow_lpm

    async def start_valve_timed(self, valve_name: str, minutes: int):
        """Start valve with timed auto-off."""
        valve = self.valves.get(valve_name)
        if not valve:
            _LOGGER.error(f"Valve {valve_name} not found")
            return

        await self._publish_state(valve_name, "ON")

        valve["session_start"] = datetime.utcnow()
        valve["session_used_l"] = 0.0
        valve["last_flow_time"] = datetime.utcnow()
        valve["mode"] = MODE_TIMED
        valve["target"] = {"minutes": minutes}

        self.hass.bus.async_fire(
            EVENT_SESSION_STARTED,
            {
                "valve": valve_name,
                "mode": MODE_TIMED,
                "target_minutes": minutes,
                "start": valve["session_start"].isoformat(),
            },
        )

        if valve["auto_off_timer"]:
            valve["auto_off_timer"]()

        async def auto_off_callback():
            await self._stop_valve(valve_name, END_REASON_AUTO_OFF)

        valve["auto_off_timer"] = self.hass.loop.call_later(
            minutes * 60, lambda: asyncio.create_task(auto_off_callback())
        )

    async def start_valve_litres(
        self, valve_name: str, litres: float, hard_timeout_min: int | None = None
    ):
        """Start valve until litres target reached."""
        valve = self.valves.get(valve_name)
        if not valve:
            _LOGGER.error(f"Valve {valve_name} not found")
            return

        await self._publish_state(valve_name, "ON")

        valve["session_start"] = datetime.utcnow()
        valve["session_used_l"] = 0.0
        valve["last_flow_time"] = datetime.utcnow()
        valve["mode"] = MODE_LITRES
        valve["target"] = {"litres": litres}

        self.hass.bus.async_fire(
            EVENT_SESSION_STARTED,
            {
                "valve": valve_name,
                "mode": MODE_LITRES,
                "target_litres": litres,
                "start": valve["session_start"].isoformat(),
            },
        )

        if valve["auto_off_timer"]:
            valve["auto_off_timer"]()

        timeout = hard_timeout_min or valve["config"].get(CONF_MAX_RUNTIME, 120)

        async def failsafe_callback():
            await self._stop_valve(valve_name, END_REASON_FAILSAFE)

        valve["auto_off_timer"] = self.hass.loop.call_later(
            timeout * 60, lambda: asyncio.create_task(failsafe_callback())
        )

    async def stop_valve(self, valve_name: str):
        """Manually stop valve."""
        await self._stop_valve(valve_name, END_REASON_MANUAL)

    async def _stop_valve(self, valve_name: str, reason: str):
        """Internal stop valve with session finalization."""
        valve = self.valves.get(valve_name)
        if not valve:
            return

        if valve["auto_off_timer"]:
            valve["auto_off_timer"]()
            valve["auto_off_timer"] = None

        await self._publish_state(valve_name, "OFF")

        await asyncio.sleep(5)

        if valve["state"] == "ON":
            _LOGGER.warning(f"Valve {valve_name} did not turn off, retrying...")
            await self._publish_state(valve_name, "OFF")

        if valve["session_start"]:
            await self._finalize_session(valve_name, reason)

    async def _finalize_session(self, valve_name: str, ended_by: str):
        """Finalize and log session."""
        valve = self.valves[valve_name]
        if not valve["session_start"]:
            return

        end = datetime.utcnow()
        duration_min = (end - valve["session_start"]).total_seconds() / 60.0
        litres = valve["session_used_l"]
        avg_lpm = litres / duration_min if duration_min > 0 else 0.0

        session = {
            "id": str(uuid.uuid4()),
            "valve": valve_name,
            "start": valve["session_start"].isoformat(),
            "end": end.isoformat(),
            "duration_min": round(duration_min, 2),
            "litres": round(litres, 2),
            "avg_lpm": round(avg_lpm, 2),
            "mode": valve["mode"] or MODE_MANUAL,
            "target": valve["target"] or {},
            "ended_by": ended_by,
            "notes": "",
        }

        self._sessions.append(session)
        await self._save_sessions()

        self.hass.bus.async_fire(
            EVENT_SESSION_ENDED,
            {
                "valve": valve_name,
                "session_id": session["id"],
                "duration_min": session["duration_min"],
                "litres": session["litres"],
                "ended_by": ended_by,
            },
        )

        valve["session_start"] = None
        valve["session_used_l"] = 0.0
        valve["mode"] = None
        valve["target"] = None

    async def _publish_state(self, valve_name: str, state: str):
        """Publish MQTT command."""
        valve = self.valves.get(valve_name)
        if not valve:
            return

        topic = valve["config"][CONF_VALVE_TOPIC] + "/set"
        payload = json.dumps({"state": state})
        await mqtt.async_publish(self.hass, topic, payload, qos=1, retain=False)

    async def reset_total(self, valve_name: str):
        """Reset total counter."""
        self._totals[valve_name] = 0.0
        await self._save_totals()
        async_dispatcher_send(self.hass, SIGNAL_VALVE_UPDATE.format(valve_name))

    def get_total(self, valve_name: str) -> float:
        """Get total litres."""
        return self._totals.get(valve_name, 0.0)

    def get_sessions(
        self,
        valve_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get filtered sessions."""
        filtered = self._sessions

        if valve_filter:
            filtered = [s for s in filtered if s["valve"] == valve_filter]

        if start_date:
            filtered = [s for s in filtered if s["start"] >= start_date]

        if end_date:
            filtered = [s for s in filtered if s["end"] <= end_date]

        return filtered

    async def delete_session(self, session_id: str):
        """Delete a session."""
        self._sessions = [s for s in self._sessions if s["id"] != session_id]
        await self._save_sessions()

    async def clear_sessions(self):
        """Clear all sessions."""
        self._sessions = []
        await self._save_sessions()

    async def _load_totals(self):
        """Load totals from storage."""
        data = await self._totals_store.async_load()
        self._totals = data or {}

    async def _save_totals(self):
        """Save totals to storage."""
        await self._totals_store.async_save(self._totals)

    async def _load_sessions(self):
        """Load sessions from storage."""
        data = await self._sessions_store.async_load()
        self._sessions = data or []

    async def _save_sessions(self):
        """Save sessions to storage."""
        await self._sessions_store.async_save(self._sessions)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Z2M Irrigation from a config entry."""
    manager = ValveManager(hass, entry)
    await manager.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _register_services(hass)
    await _register_websocket_api(hass)
    await _register_panel(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        manager: ValveManager = hass.data[DOMAIN].pop(entry.entry_id)
        await manager.async_unload()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _register_services(hass: HomeAssistant):
    """Register services."""

    async def handle_start_timed(call: ServiceCall):
        valve_name = call.data[ATTR_NAME]
        minutes = call.data[ATTR_MINUTES]

        for manager in hass.data[DOMAIN].values():
            if valve_name in manager.valves:
                await manager.start_valve_timed(valve_name, minutes)
                return

    async def handle_start_litres(call: ServiceCall):
        valve_name = call.data[ATTR_NAME]
        litres = call.data[ATTR_LITRES]
        hard_timeout = call.data.get(ATTR_HARD_TIMEOUT_MIN)

        for manager in hass.data[DOMAIN].values():
            if valve_name in manager.valves:
                await manager.start_valve_litres(valve_name, litres, hard_timeout)
                return

    async def handle_stop(call: ServiceCall):
        valve_name = call.data[ATTR_NAME]

        for manager in hass.data[DOMAIN].values():
            if valve_name in manager.valves:
                await manager.stop_valve(valve_name)
                return

    async def handle_reset_total(call: ServiceCall):
        valve_name = call.data[ATTR_NAME]

        for manager in hass.data[DOMAIN].values():
            if valve_name in manager.valves:
                await manager.reset_total(valve_name)
                return

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_TIMED,
        handle_start_timed,
        schema=vol.Schema(
            {
                vol.Required(ATTR_NAME): cv.string,
                vol.Required(ATTR_MINUTES): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_LITRES,
        handle_start_litres,
        schema=vol.Schema(
            {
                vol.Required(ATTR_NAME): cv.string,
                vol.Required(ATTR_LITRES): cv.positive_float,
                vol.Optional(ATTR_HARD_TIMEOUT_MIN): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP,
        handle_stop,
        schema=vol.Schema({vol.Required(ATTR_NAME): cv.string}),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_TOTAL,
        handle_reset_total,
        schema=vol.Schema({vol.Required(ATTR_NAME): cv.string}),
    )


async def _register_websocket_api(hass: HomeAssistant):
    """Register WebSocket API commands."""
    from .websocket import async_register_websocket_handlers

    async_register_websocket_handlers(hass)


async def _register_panel(hass: HomeAssistant):
    """Register frontend panel."""
    await hass.http.async_register_static_paths(
        [
            {
                "path": f"/{DOMAIN}/panel.js",
                "file": hass.config.path(
                    f"custom_components/{DOMAIN}/panel/panel.js"
                ),
            }
        ]
    )

    hass.components.frontend.async_register_built_in_panel(
        "iframe",
        "Irrigation Sessions",
        "mdi:water-pump",
        DOMAIN,
        {"url": f"/api/{DOMAIN}/panel"},
        require_admin=False,
    )
