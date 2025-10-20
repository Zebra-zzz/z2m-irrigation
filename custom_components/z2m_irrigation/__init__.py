from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN, PLATFORMS, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC,
    SIG_NEW_VALVE, SIG_UPDATE_VALVE, CONF_SKIP_ENTITY_ID
)

STORE_VERSION = 1

@dataclass
class ValveState:
    name: str
    running: bool = False
    last_lpm: float = 0.0
    last_ts: float | None = None
    session_started: float | None = None
    session_liters: float = 0.0
    total_liters: float = 0.0
    total_minutes: float = 0.0
    battery: int | None = None
    status: str | None = None
    ieee: str | None = None
    model: str | None = "SWV"

class ValveManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        data = entry.data or {}
        self.base = data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        self.skip_entity_id: str | None = (entry.options or {}).get(CONF_SKIP_ENTITY_ID)
        self.valves: dict[str, ValveState] = {}
        self._store = Store(hass, STORE_VERSION, f"{DOMAIN}_{entry.entry_id}.json")
        self._unsubs: list[callable] = []

    async def async_start(self) -> None:
        # Load persisted totals
        saved = await self._store.async_load() or {}
        for name, v in saved.get("valves", {}).items():
            self.valves[name] = ValveState(name=name, **v)

        # Subscribe to Z2M device list (autodiscovery)
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base}/bridge/devices", self._devices_msg
            )
        )
        # Ask Z2M to publish current devices list
        await mqtt.async_publish(self.hass, f"{self.base}/bridge/request/devices", "{}")

        # Also listen to individual device states (wildcard)
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base}/+/+", self._maybe_device_msg_wildcard
            )
        )

    async def async_stop(self) -> None:
        for u in self._unsubs: u()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({
            "valves": {
                n: {
                    "running": v.running,
                    "last_lpm": v.last_lpm,
                    "last_ts": v.last_ts,
                    "session_started": v.session_started,
                    "session_liters": v.session_liters,
                    "total_liters": v.total_liters,
                    "total_minutes": v.total_minutes,
                    "battery": v.battery,
                    "status": v.status,
                    "ieee": v.ieee,
                    "model": v.model,
                } for n, v in self.valves.items()
            }
        })

    async def _devices_msg(self, msg) -> None:
        try:
            devices = json.loads(msg.payload)
        except Exception:
            return
        for dev in devices:
            if dev.get("definition", {}).get("model") != "SWV":
                continue
            name = dev.get("friendly_name")
            if not name: continue
            if name not in self.valves:
                self.valves[name] = ValveState(name=name, ieee=dev.get("ieee_address"))
                async_dispatcher_send(self.hass, SIG_NEW_VALVE, name)
                # Subscribe to its state topic
                await mqtt.async_subscribe(self.hass, f"{self.base}/{name}", self._device_state(name))

    async def _maybe_device_msg_wildcard(self, msg) -> None:
        # Topic like base/<name> or base/<name>/get etc. We only care exact state.
        parts = msg.topic.split("/")
        if len(parts) < 2 or parts[0] != self.base: return
        name = parts[1]
        if name in self.valves and len(parts) == 2:
            cb = self._device_state(name)
            await cb(msg)

    def _device_state(self, name: str):
        async def _cb(msg) -> None:
            v = self.valves.setdefault(name, ValveState(name=name))
            try:
                data = json.loads(msg.payload)
            except Exception:
                return

            # Track on/off
            state = data.get("state")
            now = self.hass.time_time()

            # Flow (m³/h -> L/min)
            flow_m3h = data.get("flow")
            if flow_m3h is not None:
                lpm = (float(flow_m3h) * 1000.0) / 60.0
                # integrate (left rectangle)
                if v.last_ts is not None:
                    dt_s = max(0.0, now - v.last_ts)
                    v.session_liters += (v.last_lpm * dt_s) / 60.0
                    if v.running:
                        v.total_minutes += dt_s / 60.0
                v.last_lpm = lpm
                v.last_ts = now

            if state in ("ON","OFF"):
                running = (state == "ON")
                if running and not v.running:
                    v.session_started = now
                    v.session_liters = 0.0
                    v.last_ts = now
                if (not running) and v.running:
                    # close session; add to totals
                    v.total_liters += max(0.0, v.session_liters)
                    await self._save()
                v.running = running

            if "battery" in data: v.battery = data.get("battery")
            if "current_device_status" in data: v.status = data.get("current_device_status")

            async_dispatcher_send(self.hass, SIG_UPDATE_VALVE, name)
        return _cb

    async def publish(self, name: str, payload: dict) -> None:
        await mqtt.async_publish(self.hass, f"{self.base}/{name}/set", json.dumps(payload), qos=0, retain=False)

    async def turn_on(self, name: str, on_time: int | None = None) -> None:
        if name not in self.valves: return
        pl = {"state":"ON"}
        if on_time: pl["on_time"] = int(on_time)
        # optional skip
        if self.skip_entity_id:
            st = self.hass.states.get(self.skip_entity_id)
            if st and str(st.state).lower() in ("on","true","1"):
                return  # skip due to weather/rain
        await self.publish(name, pl)

    async def turn_off(self, name: str) -> None:
        if name not in self.valves: return
        await self.publish(name, {"state":"OFF"})

    async def start_liters(self, name: str, liters: float, failsafe_minutes: int = 240) -> None:
        """Start and stop automatically when session_liters >= liters."""
        await self.turn_on(name)
        target = float(liters)
        v = self.valves[name]

        async def _watch():
            # Poll every 2s, stop when reached or failsafe
            start = self.hass.time_time()
            while True:
                await asyncio.sleep(2)
                if not v.running:
                    return
                if v.session_liters >= target:
                    await self.turn_off(name)
                    return
                if self.hass.time_time() - start > failsafe_minutes*60:
                    await self.turn_off(name)
                    return
        asyncio.create_task(_watch())

    async def reset_totals(self, name: str) -> None:
        v = self.valves.get(name)
        if not v: return
        v.total_liters = 0.0
        v.total_minutes = 0.0
        await self._save()
        async_dispatcher_send(self.hass, SIG_UPDATE_VALVE, name)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mgr = ValveManager(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mgr

    await mgr.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # services
    async def _svc_start_timed(call):
        await mgr.turn_on(call.data["valve"], on_time=int(call.data["minutes"])*60)
    async def _svc_start_liters(call):
        await mgr.start_liters(call.data["valve"], float(call.data["liters"]))
    async def _svc_stop(call):
        await mgr.turn_off(call.data["valve"])
    async def _svc_reset(call):
        await mgr.reset_totals(call.data["valve"])

    hass.services.async_register(DOMAIN, "start_timed", _svc_start_timed)
    hass.services.async_register(DOMAIN, "start_liters", _svc_start_liters)
    hass.services.async_register(DOMAIN, "stop", _svc_stop)
    hass.services.async_register(DOMAIN, "reset_totals", _svc_reset)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]
    await mgr.async_stop()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
