"""Constants for Z2M Irrigation integration."""

DOMAIN = "z2m_irrigation"

CONF_VALVES = "valves"
CONF_VALVE_NAME = "valve_name"
CONF_VALVE_TOPIC = "valve_topic"
CONF_FLOW_UNIT = "flow_unit"
CONF_MAX_RUNTIME = "max_runtime"
CONF_NOISE_FLOOR = "noise_floor"

FLOW_UNIT_M3H = "m3h"
FLOW_UNIT_LPM = "lpm"

DEFAULT_MAX_RUNTIME = 120
DEFAULT_NOISE_FLOOR = 0.3

SERVICE_START_TIMED = "start_timed"
SERVICE_START_LITRES = "start_litres"
SERVICE_STOP = "stop"
SERVICE_RESET_TOTAL = "reset_total"

ATTR_NAME = "name"
ATTR_MINUTES = "minutes"
ATTR_LITRES = "litres"
ATTR_HARD_TIMEOUT_MIN = "hard_timeout_min"

SIGNAL_VALVE_UPDATE = "z2m_irrigation_valve_update_{}"

EVENT_SESSION_STARTED = "z2m_irrigation_session_started"
EVENT_SESSION_ENDED = "z2m_irrigation_session_ended"

MODE_TIMED = "timed"
MODE_LITRES = "litres"
MODE_MANUAL = "manual"

END_REASON_AUTO_OFF = "auto_off"
END_REASON_LITRES_REACHED = "litres_reached"
END_REASON_MANUAL = "manual"
END_REASON_FAILSAFE = "failsafe"
