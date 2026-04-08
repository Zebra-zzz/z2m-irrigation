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

from .const import DOMAIN
from .manager import ValveManager

_LOGGER = logging.getLogger(__name__)

_PANIC_SIGNAL = "z2m_irrigation_panic_state_changed"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    mgr: ValveManager = hass.data[DOMAIN][entry.entry_id]["manager"]
    async_add_entities([PanicSensor(mgr)])


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
