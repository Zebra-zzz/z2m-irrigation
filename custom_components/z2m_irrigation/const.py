from homeassistant.const import Platform
DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
# options
OPT_MANUAL_VALVES = "manual_valves"  # list[str] base topics (optional)
# dispatcher signal
SIG_NEW_VALVE = f"{DOMAIN}_new_valve"
