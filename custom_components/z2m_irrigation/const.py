from homeassistant.const import Platform

DOMAIN = "z2m_irrigation"

CONF_BASE_TOPIC = "base_topic"
DEFAULT_BASE_TOPIC = "zigbee2mqtt"

CONF_MANUAL_TOPICS = "manual_topics"  # newline-separated friendly names
CONF_FLOW_SCALE = "flow_scale"        # multiply incoming 'flow' to end up in L/min
DEFAULT_FLOW_SCALE = 1.0

Z2M_MODEL = "SWV"  # Sonoff smart water valve

SIG_NEW_VALVE = "z2m_irrigation_new_valve"
def sig_update(topic: str) -> str:
    return f"z2m_irrigation_update::{topic}"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

MANUFACTURER = "Sonoff"
MODEL = "SWV"
