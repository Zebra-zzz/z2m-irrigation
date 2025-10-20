from homeassistant.const import Platform

DOMAIN = "z2m_irrigation"

CONF_BASE_TOPIC = "base_topic"
DEFAULT_BASE_TOPIC = "zigbee2mqtt"

Z2M_MODEL = "SWV"  # Sonoff smart water valve (Z2M model)

SIG_NEW_VALVE = "z2m_irrigation_new_valve"
def sig_update(topic: str) -> str:
    return f"z2m_irrigation_update::{topic}"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

MANUFACTURER = "Sonoff"
MODEL = "SWV"
