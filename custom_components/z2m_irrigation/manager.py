from __future__ import annotations
import asyncio, json, time, hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import mqtt
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN, SIG_NEW_VALVE

@dataclass
class ValveState:
    base: str
    name: str
    uid:  str
    is_on: bool = False
    total_l: float = 0.0
    flow_l_min: float = 0.0
    _session_anchor_l: Optional[float] = None
    session_used_l: float = 0.0
    litres_target: Optional[float] = None
    off_handle: Optional[asyncio.TimerHandle] = None
    last_update: float = field(default_factory=time.time)

    def update_from_payload(self, payload: dict):
        st = str(payload.get("state") or payload.get("valve") or "").upper()
        if st in ("ON","OPEN","1","TRUE"): self.is_on = True
        elif st in ("OFF","CLOSE","CLOSED","0","FALSE"): self.is_on = False

        flow = payload.get("flow")
        if isinstance(flow, (int,float)):
            self.flow_l_min = float(flow) if float(flow) < 200 else float(flow)*1000/60

        # prefer m3, else litres
        found = False
        for k in ("water_consumed_m3","total_m3","meter_m3"):
            if k in payload and isinstance(payload[k], (int,float)):
                self.total_l = float(payload[k])*1000; found=True; break
        if not found:
            for k in ("total_l","litres_total","water_total_l","total","meter"):
                if k in payload and isinstance(payload[k], (int,float)):
                    self.total_l = float(payload[k]); break

        now = time.time()
        if self.is_on:
            if self._session_anchor_l is None:
                self._session_anchor_l = self.total_l or 0.0
                self.session_used_l = 0.0
            if self.total_l > 0:
                self.session_used_l = max(0.0, self.total_l - (self._session_anchor_l or 0.0))
            elif self.flow_l_min > 0:
                dt = max(0.0, now - self.last_update)
                self.session_used_l += (self.flow_l_min * dt/60.0)
        else:
            self._session_anchor_l = None
            self.session_used_l = 0.0
        self.last_update = now

class ValveManager:
    def __init__(self, hass: HomeAssistant, base_topic: str, manual_bases: List[str] | None):
        self.hass = hass
        self.base = base_topic.strip("/") or "zigbee2mqtt"
        self.disc_req = f"{self.base}/bridge/config/devices/get"
        self.disc_res = f"{self.base}/bridge/devices"
        self.valves: Dict[str, ValveState] = {}
        self._manual_bases = [b.strip("/").replace("//","/") for b in (manual_bases or [])]

    async def start(self):
        await mqtt.async_subscribe(self.hass, self.disc_res, self._devices_msg)
        # trigger retained response
        await mqtt.async_publish(self.hass, self.disc_req, "")
        # ensure manual bases
        for b in self._manual_bases:
            await self._ensure_valve(b)

    async def _ensure_valve(self, base: str, name: Optional[str]=None):
        key = base.strip("/")
        if key in self.valves:
            return
        nm = name or key.split("/")[-1]
        uid = hashlib.md5(key.encode()).hexdigest()
        v = ValveState(base=key, name=nm, uid=uid)
        self.valves[key] = v

        async def _cb(msg):
            try:
                data = json.loads(msg.payload)
            except Exception:
                data = {}
            v.update_from_payload(data)
            # litres-run cutoff
            if v.litres_target is not None and v.session_used_l >= v.litres_target and v.is_on:
                await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"}))
                v.litres_target = None
            async_dispatcher_send(self.hass, SIG_NEW_VALVE, key)

        await mqtt.async_subscribe(self.hass, key, _cb)
        async_dispatcher_send(self.hass, SIG_NEW_VALVE, key)

    @callback
    async def _devices_msg(self, msg):
        try:
            devices = json.loads(msg.payload)
        except Exception:
            return
        for d in devices:
            fn = d.get("friendly_name") or d.get("friendlyName") or ""
            if not fn:
                continue
            definition = d.get("definition") or {}
            vendor = (definition.get("vendor") or "") + (definition.get("model") or "")
            exposes = definition.get("exposes") or d.get("exposes") or []
            looks_valve = "sonoff" in vendor.lower() or any(
                (isinstance(x, dict) and str(x.get("name") or x.get("property") or "").lower() in ("state","valve","water","flow"))
                for x in (exposes if isinstance(exposes, list) else [])
            )
            if looks_valve:
                await self._ensure_valve(f"{self.base}/{fn}", fn)

    async def turn_on_for(self, base: str, minutes: int):
        v = self.valves.get(base.strip("/")); if not v: return
        await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"ON"}))
        v.litres_target = None
        if v.off_handle: v.off_handle.cancel(); v.off_handle=None
        loop = asyncio.get_running_loop()
        def _off():
            asyncio.create_task(mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"})))
            v.off_handle = None
        v.off_handle = loop.call_later(max(1, minutes*60), _off)

    async def turn_on_for_litres(self, base: str, litres: float, failsafe_minutes: int = 180):
        v = self.valves.get(base.strip("/")); if not v: return
        v.litres_target = max(0.0, float(litres))
        await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"ON"}))
        if v.off_handle: v.off_handle.cancel(); v.off_handle=None
        loop = asyncio.get_running_loop()
        def _off():
            asyncio.create_task(mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"})))
            v.off_handle=None; v.litres_target=None
        v.off_handle = loop.call_later(max(60, failsafe_minutes*60), _off)

    async def turn_off(self, base: str):
        v = self.valves.get(base.strip("/")); if not v: return
        await mqtt.async_publish(self.hass, f"{v.base}/set", json.dumps({"state":"OFF"}))
        if v.off_handle: v.off_handle.cancel(); v.off_handle=None
        v.litres_target=None
