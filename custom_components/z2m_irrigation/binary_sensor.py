"""System-level binary sensors for the z2m_irrigation integration.

v3.2 — Adds `binary_sensor.z2m_irrigation_panic`, a system-wide indicator
that turns ON when the integration enters a panic state (all software/
hardware failsafes have been exhausted and water may still be flowing).

Users wire an HA automation against this entity (or against the
EVENT_PANIC_REQUIRED bus event) to kill an upstream water pump.

State persists across HA restart via RestoreEntity, so a panic that was
active when HA went down is still active when HA comes back up.
"""

from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SIG_NEW_VALVE,
    sig_update,
    sig_zone_config_changed,
)
from .manager import ValveManager, Valve
from .zone_store import ZoneConfig

_LOGGER = logging.getLogger(__name__)

_PANIC_SIGNAL = "z2m_irrigation_panic_state_changed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    async_add_entities([
        PanicSensor(mgr),
        AnyRunningBinarySensor(mgr),
    ])

    # v4.0-alpha-3 — per-zone `in_smart_cycle` binary sensor, added once
    # for every existing valve and any future ones discovered later via
    # SIG_NEW_VALVE.
    @callback
    def _add_zone_binary(v: Valve):
        async_add_entities([ZoneInSmartCycleBinarySensor(mgr, v)], True)

    for v in list(mgr.valves.values()):
        _add_zone_binary(v)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIG_NEW_VALVE, _add_zone_binary)
    )


class PanicSensor(BinarySensorEntity, RestoreEntity):
    """System-level panic indicator.

    `on` = the integration has entered a panic state and external
    intervention is needed (kill the water pump).
    `off` = normal operation.

    State is restored from disk on HA startup so a panic that was active
    pre-restart is still active post-restart.
    """

    _attr_has_entity_name = False
    _attr_name = "z2m_irrigation panic"
    _attr_unique_id = "z2m_irrigation_panic"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:water-alert"

    def __init__(self, mgr: ValveManager) -> None:
        self.mgr = mgr
        self._unsub: Optional[callable] = None

    @property
    def is_on(self) -> bool:
        return self.mgr.panic.active

    @property
    def extra_state_attributes(self) -> dict:
        p = self.mgr.panic
        return {
            "reason": p.reason,
            "triggered_at": p.triggered_at_iso,
            "affected_valves": list(p.affected_valves),
        }

    async def async_added_to_hass(self) -> None:
        """Restore previous panic state and subscribe to update signal."""
        await super().async_added_to_hass()

        # Restore the panic state from the last HA shutdown.
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            attrs = last.attributes or {}
            self.mgr.panic.active = True
            self.mgr.panic.reason = attrs.get("reason", "restored_from_disk")
            self.mgr.panic.triggered_at_iso = attrs.get("triggered_at", "")
            self.mgr.panic.affected_valves = list(
                attrs.get("affected_valves", [])
            )
            _LOGGER.warning(
                "🚨 PanicSensor restored state: STILL IN PANIC. "
                "reason=%s, affected=%s. Clear via z2m_irrigation.clear_panic.",
                self.mgr.panic.reason, self.mgr.panic.affected_valves,
            )

        @callback
        def _on_change():
            self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(
            self.hass, _PANIC_SIGNAL, _on_change,
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None


class AnyRunningBinarySensor(BinarySensorEntity):
    """v4.0-alpha-1 — `binary_sensor.z2m_irrigation_any_running`.

    `on` when at least one valve has an active session in progress
    (`Valve.session_active`). Powers the embed card's compact running
    indicator and any user automations that need a single boolean for
    "is irrigation happening right now".

    Subscribes to per-valve `sig_update` for every valve, both the ones
    present at startup and any that arrive later via SIG_NEW_VALVE.
    """

    _attr_has_entity_name = False
    _attr_name = "Z2M Irrigation Any Running"
    _attr_unique_id = "z2m_irrigation_any_running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-pump"

    def __init__(self, mgr: ValveManager) -> None:
        self.mgr = mgr
        self._valve_unsubs: list = []
        self._unsub_new_valve: Optional[callable] = None

    @property
    def is_on(self) -> bool:
        return any(v.session_active for v in self.mgr.valves.values())

    @property
    def extra_state_attributes(self) -> dict:
        running = [
            {"valve": v.topic, "name": v.name, "session_liters": round(v.session_liters, 2)}
            for v in self.mgr.valves.values() if v.session_active
        ]
        return {"running_valves": running, "running_count": len(running)}

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_update():
            self.async_write_ha_state()

        @callback
        def _wire(v: Valve):
            self._valve_unsubs.append(
                async_dispatcher_connect(self.hass, sig_update(v.topic), _on_update)
            )

        for v in list(self.mgr.valves.values()):
            _wire(v)

        self._unsub_new_valve = async_dispatcher_connect(
            self.hass, SIG_NEW_VALVE, _wire,
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_new_valve:
            self._unsub_new_valve()
            self._unsub_new_valve = None
        for u in self._valve_unsubs:
            try:
                u()
            except Exception:
                pass
        self._valve_unsubs.clear()


class ZoneInSmartCycleBinarySensor(BinarySensorEntity):
    """v4.0-alpha-3 — per-zone `binary_sensor.<zone>_in_smart_cycle`.

    `on` when the zone is enrolled in the smart-watering cycle (i.e. its
    `ZoneConfig.in_smart_cycle` flag is True). The Setup tab on the v4.0
    dashboard surfaces this as a toggle that calls the
    `set_zone_in_smart_cycle` service.

    Subscribes to BOTH the per-valve update channel (so the binary sensor
    refreshes when the underlying valve does anything observable) AND
    the zone-config-changed channel (so service-driven edits flip the
    state instantly without waiting for the next valve event).
    """

    _attr_has_entity_name = True
    _attr_name = "In Smart Cycle"
    _attr_icon = "mdi:auto-mode"

    def __init__(self, mgr: ValveManager, valve: Valve) -> None:
        self.mgr = mgr
        self.valve = valve
        self._sig = sig_update(valve.topic)
        self._sig_cfg = sig_zone_config_changed(valve.topic)
        self._unsub: Optional[callable] = None
        self._unsub_cfg: Optional[callable] = None

    @property
    def unique_id(self) -> str:
        return f"{self.valve.topic}_in_smart_cycle".lower().replace(" ", "_")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.valve.topic)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self.valve.name,
        )

    def _zone_cfg(self) -> ZoneConfig:
        if self.mgr.zone_store is None:
            return ZoneConfig()
        return self.mgr.zone_store.get_zone(self.valve.topic)

    @property
    def is_on(self) -> bool:
        return bool(self._zone_cfg().in_smart_cycle)

    async def async_added_to_hass(self) -> None:
        @callback
        def _on_change():
            self.async_write_ha_state()

        self._unsub = async_dispatcher_connect(self.hass, self._sig, _on_change)
        self._unsub_cfg = async_dispatcher_connect(
            self.hass, self._sig_cfg, _on_change,
        )
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_cfg:
            self._unsub_cfg()
            self._unsub_cfg = None
