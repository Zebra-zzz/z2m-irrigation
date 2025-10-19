from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULT_NAME, OPT_MANUAL_VALVES, OPT_BASE_TOPIC

class Flow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=DEFAULT_NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    def async_get_options_flow(entry):
        return Options(entry)

class Options(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input=None):
        defaults = {
          OPT_BASE_TOPIC: self.entry.options.get(OPT_BASE_TOPIC, "zigbee2mqtt"),
          "manual_valves_text": "\n".join(self.entry.options.get(OPT_MANUAL_VALVES, [])),
        }
        schema = vol.Schema({
          vol.Optional(OPT_BASE_TOPIC, default=defaults[OPT_BASE_TOPIC]): str,
          vol.Optional("manual_valves_text", default=defaults["manual_valves_text"]): str,
        })
        if user_input is not None:
            lines = [ln.strip().rstrip("/") for ln in user_input.get("manual_valves_text","").splitlines() if ln.strip()]
            return self.async_create_entry(title="", data={OPT_BASE_TOPIC: user_input[OPT_BASE_TOPIC], OPT_MANUAL_VALVES: lines})
        return self.async_show_form(step_id="init", data_schema=schema)
