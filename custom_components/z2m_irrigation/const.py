from homeassistant.const import Platform
DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
OPT_MANUAL_VALVES = "manual_valves"     # list[str] (optional full base topics)
OPT_BASE_TOPIC    = "base_topic"        # e.g. "zigbee2mqtt"
SIG_NEW_VALVE = f"{DOMAIN}_new_valve"
