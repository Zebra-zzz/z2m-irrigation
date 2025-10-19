"""Sensor platform for Z2M Irrigation."""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ValveManager
from .const import DOMAIN, SIGNAL_VALVE_UPDATE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up sensor platform."""
    manager: ValveManager = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for valve_name in manager.valves:
        entities.extend(
            [
                FlowSensor(manager, valve_name, entry.entry_id),
                TotalSensor(manager, valve_name, entry.entry_id),
                SessionUsedSensor(manager, valve_name, entry.entry_id),
                BatterySensor(manager, valve_name, entry.entry_id),
                LinkQualitySensor(manager, valve_name, entry.entry_id),
            ]
        )

    async_add_entities(entities)


class BaseSensor(SensorEntity):
    """Base sensor class."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        self._manager = manager
        self._valve_name = valve_name
        self._entry_id = entry_id

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


class FlowSensor(BaseSensor):
    """Flow rate sensor."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(manager, valve_name, entry_id)
        self._attr_name = f"{valve_name} Flow"
        self._attr_unique_id = f"{entry_id}_{valve_name}_flow"
        self._attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_MINUTE
        self._attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state."""
        valve = self._manager.valves.get(self._valve_name)
        return round(valve["flow_lpm"], 2) if valve else 0.0


class TotalSensor(BaseSensor):
    """Total litres sensor."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(manager, valve_name, entry_id)
        self._attr_name = f"{valve_name} Total"
        self._attr_unique_id = f"{entry_id}_{valve_name}_total"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        """Return the state."""
        return round(self._manager.get_total(self._valve_name), 2)


class SessionUsedSensor(BaseSensor):
    """Session used litres sensor."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(manager, valve_name, entry_id)
        self._attr_name = f"{valve_name} Session Used"
        self._attr_unique_id = f"{entry_id}_{valve_name}_session_used"
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state."""
        valve = self._manager.valves.get(self._valve_name)
        return round(valve["session_used_l"], 2) if valve else 0.0


class BatterySensor(BaseSensor):
    """Battery sensor."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(manager, valve_name, entry_id)
        self._attr_name = f"{valve_name} Battery"
        self._attr_unique_id = f"{entry_id}_{valve_name}_battery"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state."""
        valve = self._manager.valves.get(self._valve_name)
        return valve["battery"] if valve and valve["battery"] is not None else None


class LinkQualitySensor(BaseSensor):
    """Link quality sensor."""

    def __init__(self, manager: ValveManager, valve_name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(manager, valve_name, entry_id)
        self._attr_name = f"{valve_name} Link Quality"
        self._attr_unique_id = f"{entry_id}_{valve_name}_linkquality"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """Return the state."""
        valve = self._manager.valves.get(self._valve_name)
        return valve["linkquality"] if valve and valve["linkquality"] is not None else None
