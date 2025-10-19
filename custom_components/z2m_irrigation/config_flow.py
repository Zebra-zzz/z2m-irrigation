from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULT_NAME, OPT_VALVES

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
        return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        default_lines = "\n".join(self.entry.options.get(OPT_VALVES, []))
        schema = vol.Schema({
            vol.Optional(
                "valves_text",
                default=default_lines
            ): str
        })
        if user_input is not None:
            lines = [ln.strip().rstrip("/") for ln in user_input["valves_text"].splitlines() if ln.strip()]
            return self.async_create_entry(title="", data={OPT_VALVES: lines})
        return self.async_show_form(step_id="init", data_schema=schema,
            description_placeholders={"hint": "One base topic per line (e.g. zigbee2mqtt/Water valve 3)"} )
