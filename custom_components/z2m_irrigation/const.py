from homeassistant.const import Platform

DOMAIN = "z2m_irrigation"
DEFAULT_NAME = "Z2M Irrigation"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_BASE_TOPIC = "base_topic"
DEFAULT_BASE_TOPIC = "zigbee2mqtt"

# Optional weather/rain skip (boolean entity that when "on" skips)
CONF_SKIP_ENTITY_ID = "skip_entity_id"

# Dispatcher signals
SIG_NEW_VALVE = "z2m_irrigation_new_valve"
SIG_UPDATE_VALVE = "z2m_irrigation_update_valve"
