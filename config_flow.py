"""Config flow for Z2M Irrigation integration."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

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
    DEFAULT_MAX_RUNTIME,
    DEFAULT_NOISE_FLOOR,
)

_LOGGER = logging.getLogger(__name__)


class Z2MIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Z2M Irrigation."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            valve_config = {
                CONF_VALVE_NAME: user_input[CONF_VALVE_NAME],
                CONF_VALVE_TOPIC: user_input[CONF_VALVE_TOPIC],
                CONF_FLOW_UNIT: user_input[CONF_FLOW_UNIT],
                CONF_MAX_RUNTIME: user_input.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
                CONF_NOISE_FLOOR: user_input.get(CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR),
            }

            return self.async_create_entry(
                title=f"Z2M Irrigation",
                data={CONF_VALVES: [valve_config]},
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_VALVE_NAME, default="Water Valve 1"): cv.string,
                vol.Required(CONF_VALVE_TOPIC, default="zigbee2mqtt/Water Valve 1"): cv.string,
                vol.Required(CONF_FLOW_UNIT, default=FLOW_UNIT_LPM): vol.In(
                    [FLOW_UNIT_LPM, FLOW_UNIT_M3H]
                ),
                vol.Optional(CONF_MAX_RUNTIME, default=DEFAULT_MAX_RUNTIME): cv.positive_int,
                vol.Optional(CONF_NOISE_FLOOR, default=DEFAULT_NOISE_FLOOR): cv.positive_float,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return Z2MIrrigationOptionsFlow(config_entry)


class Z2MIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Z2M Irrigation."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self._valves = list(
            config_entry.options.get(
                CONF_VALVES, config_entry.data.get(CONF_VALVES, [])
            )
        )
        self._editing_index = None

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_valve_list()

    async def async_step_valve_list(self, user_input=None):
        """Show valve list with add/edit/remove options."""
        if user_input is not None:
            action = user_input.get("action")

            if action == "add":
                return await self.async_step_add_valve()
            elif action.startswith("edit_"):
                self._editing_index = int(action.split("_")[1])
                return await self.async_step_edit_valve()
            elif action.startswith("remove_"):
                remove_index = int(action.split("_")[1])
                self._valves.pop(remove_index)
                return await self.async_step_valve_list()
            elif action == "done":
                return self.async_create_entry(title="", data={CONF_VALVES: self._valves})

        actions = {"done": "Save and Close", "add": "Add New Valve"}
        for i, valve in enumerate(self._valves):
            actions[f"edit_{i}"] = f"Edit: {valve[CONF_VALVE_NAME]}"
            actions[f"remove_{i}"] = f"Remove: {valve[CONF_VALVE_NAME]}"

        data_schema = vol.Schema({vol.Required("action"): vol.In(actions)})

        return self.async_show_form(step_id="valve_list", data_schema=data_schema)

    async def async_step_add_valve(self, user_input=None):
        """Add a new valve."""
        errors = {}

        if user_input is not None:
            valve_config = {
                CONF_VALVE_NAME: user_input[CONF_VALVE_NAME],
                CONF_VALVE_TOPIC: user_input[CONF_VALVE_TOPIC],
                CONF_FLOW_UNIT: user_input[CONF_FLOW_UNIT],
                CONF_MAX_RUNTIME: user_input.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
                CONF_NOISE_FLOOR: user_input.get(CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR),
            }
            self._valves.append(valve_config)
            return await self.async_step_valve_list()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_VALVE_NAME, default=""): cv.string,
                vol.Required(CONF_VALVE_TOPIC, default="zigbee2mqtt/"): cv.string,
                vol.Required(CONF_FLOW_UNIT, default=FLOW_UNIT_LPM): vol.In(
                    [FLOW_UNIT_LPM, FLOW_UNIT_M3H]
                ),
                vol.Optional(CONF_MAX_RUNTIME, default=DEFAULT_MAX_RUNTIME): cv.positive_int,
                vol.Optional(CONF_NOISE_FLOOR, default=DEFAULT_NOISE_FLOOR): cv.positive_float,
            }
        )

        return self.async_show_form(
            step_id="add_valve", data_schema=data_schema, errors=errors
        )

    async def async_step_edit_valve(self, user_input=None):
        """Edit an existing valve."""
        errors = {}
        valve = self._valves[self._editing_index]

        if user_input is not None:
            self._valves[self._editing_index] = {
                CONF_VALVE_NAME: user_input[CONF_VALVE_NAME],
                CONF_VALVE_TOPIC: user_input[CONF_VALVE_TOPIC],
                CONF_FLOW_UNIT: user_input[CONF_FLOW_UNIT],
                CONF_MAX_RUNTIME: user_input.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
                CONF_NOISE_FLOOR: user_input.get(CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR),
            }
            self._editing_index = None
            return await self.async_step_valve_list()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_VALVE_NAME, default=valve[CONF_VALVE_NAME]): cv.string,
                vol.Required(CONF_VALVE_TOPIC, default=valve[CONF_VALVE_TOPIC]): cv.string,
                vol.Required(CONF_FLOW_UNIT, default=valve[CONF_FLOW_UNIT]): vol.In(
                    [FLOW_UNIT_LPM, FLOW_UNIT_M3H]
                ),
                vol.Optional(
                    CONF_MAX_RUNTIME, default=valve.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
                ): cv.positive_int,
                vol.Optional(
                    CONF_NOISE_FLOOR, default=valve.get(CONF_NOISE_FLOOR, DEFAULT_NOISE_FLOOR)
                ): cv.positive_float,
            }
        )

        return self.async_show_form(
            step_id="edit_valve", data_schema=data_schema, errors=errors
        )
