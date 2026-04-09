"""Config flow for z2m_irrigation.

v4.0-alpha-1 — rewritten as a 3-step options flow:
  Step 1 (init)    — MQTT base topic, manual topics, flow scale.
  Step 2 (weather) — VPD / rain-today / forecast-24h / temp entity ids.
  Step 3 (safety)  — Kill switch entity, mode, global skip thresholds.

The initial setup step (`async_step_user`) is intentionally trivial: it
just creates the config entry. All actual configuration happens in the
options flow, which is reachable from Settings → Devices & Services →
Z2M Irrigation → Configure. This pattern matches every step's "live
edit" semantics with no extra UI for first-time setup.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_BASE_TOPIC,
    DEFAULT_BASE_TOPIC,
    CONF_MANUAL_TOPICS,
    CONF_FLOW_SCALE,
    DEFAULT_FLOW_SCALE,
    CONF_WEATHER_VPD_ENTITY,
    CONF_WEATHER_RAIN_TODAY_ENTITY,
    CONF_WEATHER_RAIN_FORECAST_24H_ENTITY,
    CONF_WEATHER_TEMP_ENTITY,
    CONF_KILL_SWITCH_ENTITY,
    CONF_KILL_SWITCH_MODE,
    CONF_GLOBAL_SKIP_RAIN_MM,
    CONF_GLOBAL_SKIP_FORECAST_MM,
    CONF_GLOBAL_MIN_RUN_LITERS,
    KILL_SWITCH_MODES,
    DEFAULT_KILL_SWITCH_MODE,
    DEFAULT_GLOBAL_SKIP_RAIN_MM,
    DEFAULT_GLOBAL_SKIP_FORECAST_MM,
    DEFAULT_GLOBAL_MIN_RUN_LITERS,
)


class Z2MIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup — single trivial step that just creates the entry."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Z2M Irrigation", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """v4.0-alpha-1 — 3-step options flow.

    Each step accumulates into `self._collected` and chains forward by
    returning the next step's coroutine. The final step calls
    `async_create_entry` with the merged dict, which atomically replaces
    the entry's options.
    """

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        # Start from the existing options so unmodified fields keep their
        # current value across the flow.
        self._collected: Dict[str, Any] = dict(entry.options)

    # ─────────────────────────────────────────────────────────────────────
    # Step 1 — MQTT (existing v3.x fields)
    # ─────────────────────────────────────────────────────────────────────

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            self._collected.update(user_input)
            return await self.async_step_weather()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_BASE_TOPIC,
                    default=self._collected.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
                ): str,
                vol.Optional(
                    CONF_MANUAL_TOPICS,
                    default=self._collected.get(CONF_MANUAL_TOPICS, ""),
                ): str,
                vol.Optional(
                    CONF_FLOW_SCALE,
                    default=float(self._collected.get(CONF_FLOW_SCALE, DEFAULT_FLOW_SCALE)),
                ): vol.Coerce(float),
            }),
            description_placeholders={"step": "1 / 3"},
        )

    # ─────────────────────────────────────────────────────────────────────
    # Step 2 — Weather sources (all optional)
    # ─────────────────────────────────────────────────────────────────────

    async def async_step_weather(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            # Empty strings from the entity selector → store as None so
            # the calculator can detect "missing" cleanly.
            for key in (
                CONF_WEATHER_VPD_ENTITY,
                CONF_WEATHER_RAIN_TODAY_ENTITY,
                CONF_WEATHER_RAIN_FORECAST_24H_ENTITY,
                CONF_WEATHER_TEMP_ENTITY,
            ):
                if user_input.get(key) in ("", None):
                    user_input[key] = None
            self._collected.update(user_input)
            return await self.async_step_safety()

        sensor_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )

        return self.async_show_form(
            step_id="weather",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_WEATHER_VPD_ENTITY,
                    description={
                        "suggested_value": self._collected.get(CONF_WEATHER_VPD_ENTITY) or "",
                    },
                ): sensor_selector,
                vol.Optional(
                    CONF_WEATHER_RAIN_TODAY_ENTITY,
                    description={
                        "suggested_value": self._collected.get(CONF_WEATHER_RAIN_TODAY_ENTITY) or "",
                    },
                ): sensor_selector,
                vol.Optional(
                    CONF_WEATHER_RAIN_FORECAST_24H_ENTITY,
                    description={
                        "suggested_value": self._collected.get(CONF_WEATHER_RAIN_FORECAST_24H_ENTITY) or "",
                    },
                ): sensor_selector,
                vol.Optional(
                    CONF_WEATHER_TEMP_ENTITY,
                    description={
                        "suggested_value": self._collected.get(CONF_WEATHER_TEMP_ENTITY) or "",
                    },
                ): sensor_selector,
            }),
            description_placeholders={"step": "2 / 3"},
        )

    # ─────────────────────────────────────────────────────────────────────
    # Step 3 — Safety + global thresholds (kill switch lives here)
    # ─────────────────────────────────────────────────────────────────────

    async def async_step_safety(self, user_input: Optional[Dict[str, Any]] = None):
        if user_input is not None:
            if user_input.get(CONF_KILL_SWITCH_ENTITY) in ("", None):
                user_input[CONF_KILL_SWITCH_ENTITY] = None
            self._collected.update(user_input)
            return self.async_create_entry(title="", data=self._collected)

        kill_switch_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
        )
        mode_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": m, "label": m.replace("_", " ").title()}
                    for m in KILL_SWITCH_MODES
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        return self.async_show_form(
            step_id="safety",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_KILL_SWITCH_ENTITY,
                    description={
                        "suggested_value": self._collected.get(CONF_KILL_SWITCH_ENTITY) or "",
                    },
                ): kill_switch_selector,
                vol.Optional(
                    CONF_KILL_SWITCH_MODE,
                    default=self._collected.get(CONF_KILL_SWITCH_MODE, DEFAULT_KILL_SWITCH_MODE),
                ): mode_selector,
                vol.Optional(
                    CONF_GLOBAL_SKIP_RAIN_MM,
                    default=float(self._collected.get(
                        CONF_GLOBAL_SKIP_RAIN_MM, DEFAULT_GLOBAL_SKIP_RAIN_MM,
                    )),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
                vol.Optional(
                    CONF_GLOBAL_SKIP_FORECAST_MM,
                    default=float(self._collected.get(
                        CONF_GLOBAL_SKIP_FORECAST_MM, DEFAULT_GLOBAL_SKIP_FORECAST_MM,
                    )),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
                vol.Optional(
                    CONF_GLOBAL_MIN_RUN_LITERS,
                    default=float(self._collected.get(
                        CONF_GLOBAL_MIN_RUN_LITERS, DEFAULT_GLOBAL_MIN_RUN_LITERS,
                    )),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1000.0)),
            }),
            description_placeholders={"step": "3 / 3"},
        )


# Module-level helper kept for backwards compat (older HA versions look
# for this top-level symbol; current versions use the @staticmethod above).
async def async_get_options_flow(config_entry: ConfigEntry):
    return OptionsFlowHandler(config_entry)
