from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC

class Z2MIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Z2M Irrigation", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: ConfigEntry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        base = self.entry.options.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_BASE_TOPIC, default=base): str,
            }),
        )

async def async_get_options_flow(config_entry: ConfigEntry):
    return OptionsFlowHandler(config_entry)
