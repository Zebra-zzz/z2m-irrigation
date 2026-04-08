"""Weather sensor adapter.

v4.0-alpha-1 — reads the user-configured weather entities (set via the
config flow's "Weather sources" step) and produces a `WeatherInputs`
struct for the calculator. Missing or unavailable sensors gracefully
yield `None`, which the calculator interprets as a neutral value.

v4.0-rc-2 — added unit-aware conversion. The calculator wants VPD in
kPa and rain in mm; many real-world sensors expose VPD in hPa (Ecowitt
GW2000C is one) or rain in inches (US weather stations). Without
conversion, a 0.94 kPa VPD reported as 9.4 hPa would be interpreted as
9.4 kPa and slam the dryness factor against its ceiling, dramatically
over-watering. The new conversion path reads each entity's
`unit_of_measurement` attribute and applies the appropriate scale
factor before handing the value to the calculator. Unknown units are
passed through with a warning so the user is told what to fix.

The integration ships with no built-in weather provider — the user
wires in whatever they already have (BoM, OpenWeatherMap, Ecowitt,
AccuWeather, a custom template helper, etc.). This keeps v4.0
decoupled from any one weather source AND tolerates that source's
choice of units.
"""

from __future__ import annotations

import logging
from typing import Mapping, Optional

from homeassistant.core import HomeAssistant

from .calculator import WeatherInputs

_LOGGER = logging.getLogger(__name__)


_UNAVAILABLE_STATES = {"unknown", "unavailable", "none", "", None}


# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion tables
#
# Each table maps a normalized (lowercased, trimmed) unit string from
# `state.attributes.unit_of_measurement` to a multiplier that converts
# the raw value into the target unit. e.g. 9.38 hPa × 0.1 = 0.938 kPa.
#
# Tables are conservative: only well-known unit spellings get a real
# multiplier. Anything else logs a warning and the value is passed
# through unchanged so the user knows to either pick a different
# entity or extend this table via a future patch.
# ─────────────────────────────────────────────────────────────────────────────

# Pressure → kPa (used for VPD)
_PRESSURE_TO_KPA: Mapping[str, float] = {
    "kpa": 1.0,
    "hpa": 0.1,        # 1 hPa  = 0.1 kPa  — Ecowitt, BoM, OpenWeatherMap default
    "mbar": 0.1,       # 1 mbar = 1 hPa
    "millibar": 0.1,
    "pa": 0.001,       # 1 Pa   = 0.001 kPa
    "bar": 100.0,      # 1 bar  = 100 kPa  — uncommon for VPD but cheap to support
    "psi": 6.894757,   # 1 psi  = 6.894757 kPa
    "atm": 101.325,    # 1 atm  = 101.325 kPa — extremely uncommon
    "mmhg": 0.133322,  # 1 mmHg = 0.133322 kPa — torr equivalent
    "inhg": 3.386389,  # 1 inHg = 3.386389 kPa — common on US weather stations
}

# Length → mm (used for rain today + rain forecast 24h)
_LENGTH_TO_MM: Mapping[str, float] = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "millimetre": 1.0,
    "millimetres": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "centimetre": 10.0,
    "centimetres": 10.0,
    "m": 1000.0,        # uncommon for rain but cheap to support
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    '"': 25.4,
    "ft": 304.8,        # extremely uncommon, but possible (snow accumulation?)
    "feet": 304.8,
}


def _normalize_unit(unit: Optional[str]) -> str:
    """Lowercase + strip an entity's unit_of_measurement for table lookup."""
    if unit is None:
        return ""
    return str(unit).strip().lower()


def _read_float_raw(
    hass: HomeAssistant, entity_id: Optional[str]
) -> Optional[tuple[float, str]]:
    """Read (numeric_state, normalized_unit) or None if unavailable.

    Pulled out so the unit-aware conversion path and the legacy
    pass-through (`_read_float`) can share the parsing + null-handling.
    """
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
        value = float(state.state)
    except (ValueError, TypeError):
        _LOGGER.debug(
            "weather: entity %s state %r is not numeric",
            entity_id, state.state,
        )
        return None
    unit = (state.attributes or {}).get("unit_of_measurement", "")
    return value, _normalize_unit(unit)


def _convert_via_table(
    entity_id: Optional[str],
    parsed: Optional[tuple[float, str]],
    table: Mapping[str, float],
    target_label: str,
) -> Optional[float]:
    """Apply a conversion table; pass through with a warning on unknown unit.

    Logs are deduplicated per entity_id + unit pair via the standard
    `_LOGGER.warning` mechanism — HA's logger collapses duplicates
    naturally, so a stuck unknown unit only warns on first sight per
    integration restart, not on every 15-min refresh.
    """
    if parsed is None:
        return None
    value, unit = parsed
    if not unit:
        # Sensor reports no unit at all — pass through and warn ONCE.
        _LOGGER.warning(
            "weather: %s reports no unit_of_measurement — assuming target "
            "unit %s. Set the unit on the source sensor or use a template "
            "to convert.",
            entity_id, target_label,
        )
        return value
    multiplier = table.get(unit)
    if multiplier is None:
        _LOGGER.warning(
            "weather: %s reports unknown unit %r — passing value through "
            "unchanged. Add the unit to the conversion table in weather.py "
            "or use a template sensor to convert to %s.",
            entity_id, unit, target_label,
        )
        return value
    converted = value * multiplier
    if multiplier != 1.0:
        _LOGGER.debug(
            "weather: %s %s %s → %s %s (×%s)",
            entity_id, value, unit, converted, target_label, multiplier,
        )
    return converted


def _read_pressure_kpa(
    hass: HomeAssistant, entity_id: Optional[str]
) -> Optional[float]:
    """Read a pressure entity and convert to kPa via the unit table."""
    return _convert_via_table(
        entity_id,
        _read_float_raw(hass, entity_id),
        _PRESSURE_TO_KPA,
        "kPa",
    )


def _read_length_mm(
    hass: HomeAssistant, entity_id: Optional[str]
) -> Optional[float]:
    """Read a length/rain entity and convert to mm via the unit table."""
    return _convert_via_table(
        entity_id,
        _read_float_raw(hass, entity_id),
        _LENGTH_TO_MM,
        "mm",
    )


def _read_float(hass: HomeAssistant, entity_id: Optional[str]) -> Optional[float]:
    """Read a numeric state without unit conversion. Used for the
    display-only `temp_c` field where HA already standardizes °C across
    integrations and the calculator doesn't act on the value.
    """
    parsed = _read_float_raw(hass, entity_id)
    return parsed[0] if parsed else None


def read_inputs(
    hass: HomeAssistant,
    *,
    vpd_entity: Optional[str],
    rain_today_entity: Optional[str],
    rain_forecast_24h_entity: Optional[str],
    temp_entity: Optional[str] = None,
) -> WeatherInputs:
    """Snapshot the configured weather entities right now, with unit conversion.

    VPD is converted to kPa, rain values to mm. Temperature passes
    through unchanged (display only). Returns a `WeatherInputs` with
    `None` for any sensor that is missing or unavailable.
    """
    return WeatherInputs(
        vpd_kpa=_read_pressure_kpa(hass, vpd_entity),
        rain_today_mm=_read_length_mm(hass, rain_today_entity),
        fc24_mm=_read_length_mm(hass, rain_forecast_24h_entity),
        temp_c=_read_float(hass, temp_entity),
    )
