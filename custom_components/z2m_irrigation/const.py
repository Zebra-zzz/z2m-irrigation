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

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]

MANUFACTURER = "Sonoff"
MODEL = "SWV"

# ─────────────────────────────────────────────────────────────────────────────
# v3.1 — Safety guardrail constants
# ─────────────────────────────────────────────────────────────────────────────

# How often the periodic guardrail loop runs (independent of MQTT messages).
GUARDRAIL_CHECK_INTERVAL_SECONDS = 30

# Layer 1 — Volume overshoot cap. Force OFF when session_liters exceeds
# target_liters by this multiplier. Acts as a safety net if the primary
# at-target failsafe (in _on_state) sends OFF but the device fails to respond.
GUARDRAIL_OVERSHOOT_RATIO = 1.25

# Layer 2 — Stuck-flow detection. If a session has been active for this long
# with zero progress (session_liters has not increased), assume the valve never
# physically opened or the flow sensor is broken, force OFF, and alert.
GUARDRAIL_STUCK_FLOW_TIMEOUT_SECONDS = 600  # 10 minutes

# Layer 3 — MQTT silence detection. If no MQTT message has been received from
# a device for this long while a session is active, the device is presumed
# offline (Zigbee dropout, dead battery, hardware failure). Force OFF
# (best-effort, may not reach the device) and alert the user.
GUARDRAIL_MQTT_SILENCE_TIMEOUT_SECONDS = 300  # 5 minutes

# Layer 4 — Expected duration warning. Calculated as
# (target_liters / historical_avg_flow_lpm) * this multiplier. When elapsed
# exceeds this, log a warning and fire an event but do NOT force OFF (this is
# informational only, intended to surface degradation like a clogged filter).
GUARDRAIL_EXPECTED_DURATION_WARN_RATIO = 1.5

# Number of recent completed sessions to look at when computing the historical
# average flow rate for a valve (used by Layer 4).
HISTORICAL_FLOW_LOOKBACK_SESSIONS = 5

# ─────────────────────────────────────────────────────────────────────────────
# v3.1 — OFF retry / confirmation cadence
# ─────────────────────────────────────────────────────────────────────────────

# Cumulative seconds (since the first OFF attempt) at which to re-check the
# valve state and re-issue OFF if it has not yet transitioned. Each successive
# entry escalates: warnings → notifications → critical alert.
OFF_RETRY_SCHEDULE_SECONDS = [3, 8, 15, 30, 60, 120, 180, 240, 300]

# After this many seconds without confirmation, give up retrying (the failsafe
# will fire a critical persistent_notification and HA event for manual
# intervention).
OFF_RETRY_MAX_DURATION_SECONDS = 300  # 5 minutes

# Event names fired on the HA bus for automation hooks.
EVENT_SHUTOFF_INITIATED = "z2m_irrigation_shutoff_initiated"
EVENT_SHUTOFF_CONFIRMED = "z2m_irrigation_shutoff_confirmed"
EVENT_SHUTOFF_FAILED = "z2m_irrigation_shutoff_failed"
EVENT_ORPHANED_SESSION_RECOVERED = "z2m_irrigation_orphaned_session_recovered"
