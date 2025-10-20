from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import DOMAIN, DEFAULT_NAME, CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, CONF_SKIP_ENTITY_ID

class Z2MFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data={
                CONF_BASE_TOPIC: user_input.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
            })
        schema = vol.Schema({
            vol.Optional(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @callback
    def async_get_options_flow(self, entry):
        return OptionsFlow(entry)

class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry): self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        schema = vol.Schema({
            vol.Optional(CONF_SKIP_ENTITY_ID, default=self.entry.options.get(CONF_SKIP_ENTITY_ID, "")):
                EntitySelector(EntitySelectorConfig(domain=None))
        })
        return self.async_show_form(step_id="init", data_schema=schema)
