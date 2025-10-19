from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import (
    DOMAIN, DEFAULT_NAME, DEFAULT_BASE_TOPIC,
    CONF_BASE_TOPIC, CONF_MANUAL_BASES,
)

class Z2MIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    def async_get_options_flow(config_entry):
        return Z2MOptionsFlow(config_entry)

class Z2MOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        return await self.async_step_basic(user_input)

    async def async_step_basic(self, user_input=None):
        if user_input is not None:
            base = user_input.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC).strip("/")
            manual_raw = (user_input.get(CONF_MANUAL_BASES, "") or "")
            # accept newline- or comma-separated
            manual = [s.strip().strip("/") for s in manual_raw.replace("\r","").replace(",", "\n").splitlines() if s.strip()]
            return self.async_create_entry(title="", data={
                CONF_BASE_TOPIC: base or DEFAULT_BASE_TOPIC,
                CONF_MANUAL_BASES: manual,
            })
        cur = self.entry.options or {}
        base = cur.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
        manual_list = cur.get(CONF_MANUAL_BASES, [])
        manual_text = "\n".join(manual_list) if isinstance(manual_list, list) else str(manual_list)
        schema = vol.Schema({
            vol.Optional(CONF_BASE_TOPIC, default=base): str,
            vol.Optional(CONF_MANUAL_BASES, default=manual_text): str,
        })
        return self.async_show_form(step_id="basic", data_schema=schema)
