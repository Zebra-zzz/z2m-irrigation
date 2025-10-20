from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, DEFAULT_NAME, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, CONF_MANUAL_VALVES

class Z2MIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # Normalize manual valves into newline string (HA will store as str)
            manual_raw = user_input.get(CONF_MANUAL_VALVES, "")
            if isinstance(manual_raw, list):
                manual_raw = "\n".join(x.strip() for x in manual_raw if x.strip())
            return self.async_create_entry(title="", data={
                CONF_BASE_TOPIC: user_input.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip(),
                CONF_MANUAL_VALVES: manual_raw,
            })

        opts = self.entry.options or {}
        schema = vol.Schema({
            vol.Required(CONF_BASE_TOPIC, default=opts.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)): str,
            vol.Optional(CONF_MANUAL_VALVES, default=opts.get(CONF_MANUAL_VALVES, "")): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
