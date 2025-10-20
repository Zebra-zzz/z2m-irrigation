from homeassistant.const import Platform

DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_BASE_TOPIC = "base_topic"
CONF_MANUAL_VALVES = "manual_valves"

DEFAULT_BASE_TOPIC = "zigbee2mqtt"

SIG_NEW_VALVE = f"{DOMAIN}_new_valve"
