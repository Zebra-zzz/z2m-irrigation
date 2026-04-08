"""Weather sensor adapter.

v4.0-alpha-1 — reads the user-configured weather entities (set via the
config flow's "Weather sources" step) and produces a `WeatherInputs`
struct for the calculator. Missing or unavailable sensors gracefully
yield `None`, which the calculator interprets as a neutral value.

The integration ships with no built-in weather provider — the user wires
in whatever they already have (BoM, OpenWeatherMap, AccuWeather, a custom
template helper, etc.). This keeps v4.0 decoupled from any one weather
source.
"""

from __future__ import annotations

import logging
from typing import Optional

from homeassistant.core import HomeAssistant

from .calculator import WeatherInputs

_LOGGER = logging.getLogger(__name__)


_UNAVAILABLE_STATES = {"unknown", "unavailable", "none", "", None}


def _read_float(hass: HomeAssistant, entity_id: Optional[str]) -> Optional[float]:
    """Read a numeric state, returning None if missing/invalid/unavailable."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        _LOGGER.debug("weather: entity %s not found", entity_id)
        return None
    if state.state in _UNAVAILABLE_STATES:
        _LOGGER.debug("weather: entity %s is %s", entity_id, state.state)
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        _LOGGER.debug(
            "weather: entity %s state %r is not numeric", entity_id, state.state
        )
        return None


def read_inputs(
    hass: HomeAssistant,
    *,
    vpd_entity: Optional[str],
    rain_today_entity: Optional[str],
    rain_forecast_24h_entity: Optional[str],
    temp_entity: Optional[str] = None,
) -> WeatherInputs:
    """Snapshot the configured weather entities right now.

    Returns a `WeatherInputs` with `None` for any sensor that is missing
    or unavailable. The calculator handles the `None`s — see
    `WeatherInputs.effective_*` properties.
    """
    return WeatherInputs(
        vpd_kpa=_read_float(hass, vpd_entity),
        rain_today_mm=_read_float(hass, rain_today_entity),
        fc24_mm=_read_float(hass, rain_forecast_24h_entity),
        temp_c=_read_float(hass, temp_entity),
    )
