from __future__ import annotations
import asyncio, json, time, hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN, SIG_NEW_VALVE, OPT_MANUAL_VALVES

DISCOVERY_REQ = "zigbee2mqtt/bridge/config/devices/get"
DISCOVERY_RES = "zigbee2mqtt/bridge/devices"
BASE = "zigbee2mqtt"  # typical; we derive full base as f"{BASE}/{friendly_name}"

@dataclass
class ValveState:
    base: str            # e.g. "zigbee2mqtt/Water valve 3"
    name: str            # friendly name
    uid:  str            # unique id seed
    is_on: bool = False
    total_l: float = 0.0
    flow_l_min: float = 0.0
    _last_total_l: float = 0.0
    _session_anchor_l: Optional[float] = None
    session_used_l: float = 0.0
    last_update: float = field(default_factory=time.time)
    litres_target: Optional[float] = None
    off_handle: Optional[asyncio.TimerHandle] = None

    def update_from_payload(self, payload: dict):
        # state
        st = str(payload.get("state") or payload.get("valve") or "").upper()
        if st in ("ON","OPEN","1","TRUE"): self.is_on = True
        elif st in ("OFF","CLOSE","CLOSED","0","FALSE"): self.is_on = False

        # flow: accept 'flow' in m3/h or L/min
        flow = payload.get("flow")
        if isinstance(flow, (int, float)):
            # Heuristic: if value is small (<200) and not crazy, assume L/min; else m3/h
            self.flow_l_min = float(flow) if float(flow) < 200 else float(flow)*1000/60

        # totals from many possible keys (prefer metres to litres and convert)
        for k in ("water_consumed_m3","water_consumed","total_m3","meter_m3","meter","total"):
            if k in payload and isinstance(payload[k], (int,float)):
                val = float(payload[k])
                self.total_l = val*1000 if "m3" in k or val < 50 and k in ("meter","total") else val
                break
        # also accept explicit litres fields
        for k in ("total_l","litres_total","water_total_l","total_litres"):
            if k in payload and isinstance(payload[k], (int,float)):
                self.total_l = float(payload[k]); break

        now = time.time()
        if self.is_on:
            if self._session_anchor_l is None:
                self._session_anchor_l = self.total_l or 0.0
                self.session_used_l = 0.0
            # if total available, use it; else integrate flow crudely
            if self.total_l > 0:
                diff = max(0.0, self.total_l - (self._session_anchor_l or 0.0))
                self.session_used_l = diff
            elif self.flow_l_min > 0:
                dt = max(0.0, now - self.last_update)
                self.session_used_l += (self.flow_l_min * dt/60.0)
        else:
            self._session_anchor_l = None
            self.session_used_l = 0.0
        self.last_update = now

class ValveManager:
    def __init__(self, hass: HomeAssistant, manual_bases: List[str] | None):
        self.hass = hass
        self.valves: Dict[str, ValveState] = {}
        self._discovery_task: Optional[asyncio.Task] = None
        self._manual_bases = [b.strip("/").replace("//","/") for b in (manual_bases or [])]

    async def start(self):
        # Subscribe to bridge devices list
        await mqtt.async_subscribe(self.hass, DISCOVERY_RES, self._devices_msg)
        # Ask for devices (retained)
        await mqtt.async_publish(self.hass, DISCOVERY_REQ, "")
        # Also wire up manual bases if any
        for b in self._manual_bases:
            await self._ensure_valve(f"{b}")

    async def _ensure_valve(self, base: str, name: Optional[str]=None):
        key = base.strip("/")
        if key in self.valves:
            return
        nm = name or key.split("/")[-1]
        uid = hashlib.md5(key.encode()).hexdigest()
        v = ValveState(base=key, name=nm, uid=uid)
        self.valves[key] = v

        # Subscribe to the device state topic
        async def _cb(msg):
            try:
                data = json.loads(msg.payload)
            except Exception:
                data = {}
            v.update_from_payload(data)
            # if litre target is set and met, request off
            if v.litres_target is not None and v.session_used_l >= v.litres_target and v.is_on:
                await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"}))
                v.litres_target = None
            async_dispatcher_send(self.hass, SIG_NEW_VALVE, key)
        await mqtt.async_subscribe(self.hass, key, _cb)

        # advertise to platforms
        async_dispatcher_send(self.hass, SIG_NEW_VALVE, key)

    @callback
    async def _devices_msg(self, msg):
        try:
            devices = json.loads(msg.payload)
        except Exception:
            return
        for d in devices:
            fn = d.get("friendly_name") or d.get("friendlyName") or ""
            vendor = (d.get("definition") or {}).get("vendor","")
            model = (d.get("definition") or {}).get("model","")
            exposes = (d.get("definition") or {}).get("exposes") or d.get("exposes") or []
            # Accept Sonoff water valve or anything exposing "state" and some water/flow info
            looks_valve = "valve" in (str(model)+str(vendor)).lower() or any(
                (isinstance(x, dict) and str(x.get("name") or x.get("property") or "").lower() in ("state","valve","water","flow"))
                for x in (exposes if isinstance(exposes, list) else [])
            )
            if fn and looks_valve:
                await self._ensure_valve(f"{BASE}/{fn}", fn)

    # Services:
    async def turn_on_for(self, base: str, minutes: int):
        v = self.valves.get(base.strip("/"))
        if not v:
            return
        await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"ON"}))
        v.litres_target = None
        # cancel existing timer
        if v.off_handle:
            v.off_handle.cancel()
            v.off_handle = None
        loop = asyncio.get_running_loop()
        def _off():
            asyncio.create_task(mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"})))
            v.off_handle = None
        v.off_handle = loop.call_later(max(1, minutes*60), _off)

    async def turn_on_for_litres(self, base: str, litres: float, failsafe_minutes: int = 180):
        v = self.valves.get(base.strip("/"))
        if not v:
            return
        v.litres_target = max(0.0, float(litres))
        await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"ON"}))
        # failsafe timer
        if v.off_handle:
            v.off_handle.cancel()
            v.off_handle = None
        loop = asyncio.get_running_loop()
        def _off():
            asyncio.create_task(mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"})))
            v.off_handle = None
            v.litres_target = None
        v.off_handle = loop.call_later(max(60, failsafe_minutes*60), _off)
