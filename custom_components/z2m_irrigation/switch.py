"""Switch platform for Z2M Irrigation."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ValveManager
from .const import DOMAIN, SIGNAL_VALVE_UPDATE, MODE_MANUAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up switch platform."""
    manager: ValveManager = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for valve_name in manager.valves:
        entities.append(ValveSwitch(manager, valve_name, entry.entry_id))

    async_add_entities(entities)


class ValveSwitch(SwitchEntity):
    """Representation of a valve switch."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the switch."""
        self._manager = manager
        self._valve_name = valve_name
        self._entry_id = entry_id
        self._attr_name = valve_name
        self._attr_unique_id = f"{entry_id}_{valve_name}_switch"

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_{self._valve_name}")},
            "name": self._valve_name,
            "manufacturer": "Sonoff",
            "model": "Zigbee Water Valve",
            "via_device": (DOMAIN, self._entry_id),
        }

    @property
    def is_on(self):
        """Return true if valve is on."""
        valve = self._manager.valves.get(self._valve_name)
        return valve["state"] == "ON" if valve else False

    async def async_turn_on(self, **kwargs):
        """Turn the valve on."""
        valve = self._manager.valves.get(self._valve_name)
        if valve:
            valve["mode"] = MODE_MANUAL
            await self._manager._publish_state(self._valve_name, "ON")

    async def async_turn_off(self, **kwargs):
        """Turn the valve off."""
        await self._manager.stop_valve(self._valve_name)

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_VALVE_UPDATE.format(self._valve_name),
                self._update_callback,
            )
        )

    @callback
    def _update_callback(self):
        """Update the entity."""
        self.async_write_ha_state()
