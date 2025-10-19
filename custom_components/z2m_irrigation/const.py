from homeassistant.const import Platform
DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"
PLATFORMS = [Platform.SWITCH]
OPT_VALVES = "valves"  # list[str] of base topics, e.g. "zigbee2mqtt/Water valve 3"
