from homeassistant.const import Platform

DOMAIN = "z2m_irrigation"

# Options
CONF_BASE_TOPIC = "base_topic"
CONF_MANUAL_VALVES = "manual_valves"

DEFAULT_BASE_TOPIC = "zigbee2mqtt"

# Zigbee2MQTT model filter
Z2M_MODEL = "SWV"  # Sonoff smart water valve

# Dispatcher signals
SIG_NEW_VALVE = "z2m_irrigation_new_valve"
def sig_update(topic: str) -> str:
    return f"z2m_irrigation_update::{topic}"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

MANUFACTURER = "Sonoff"
MODEL = "SWV"
