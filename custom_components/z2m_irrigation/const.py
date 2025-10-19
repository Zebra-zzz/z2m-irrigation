from homeassistant.const import Platform
DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"
DEFAULT_BASE_TOPIC = "zigbee2mqtt"
CONF_BASE_TOPIC = "base_topic"
CONF_MANUAL_BASES = "manual_bases"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]
SIG_NEW_VALVE = f"{DOMAIN}_new_valve"
