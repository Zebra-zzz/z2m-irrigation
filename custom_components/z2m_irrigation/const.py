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

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,  # v3.2 — panic indicator
]

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

# ─────────────────────────────────────────────────────────────────────────────
# v3.2 — Hardware-primary control
#
# Background: extensive testing on 2026-04-08 against the Sonoff SWV revealed:
#   1. The device's cyclic_quantitative_irrigation hardware counter is
#      highly accurate (~2.5% vs bucket measurement) when used in isolation
#   2. The device's cyclic_timed_irrigation hardware timer is accurate to ±2s
#   3. The device exposes its own flow only at 1-decimal m³/h precision,
#      causing software flow integration to be ±10-40% inaccurate depending
#      on actual flow rate
#
# Conclusion: shift the architecture so that the device's hardware features
# are the PRIMARY control mechanism, and software is a monitor/backup.
#
# v3.2.1 follow-up findings: cyclic_quantitative_irrigation and
# cyclic_timed_irrigation CANNOT coexist on this firmware. Setting one
# clears the other (both as a combined payload, AND as sequential MQTT
# publishes). The two hardware modes are mutually exclusive.
#
# Therefore:
#   * start_liters() uses ONLY cyclic_quantitative_irrigation
#   * start_timed() uses ONLY cyclic_timed_irrigation (existing v3.1 behavior)
#   * No "hardware time backstop for volume runs" — software guardrails
#     1-3 (stuck-flow, MQTT-silence, 140% overshoot) plus the panic system
#     are the safety nets for a stuck-volume-mode scenario.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# v3.2 — Software 140% overshoot guardrail
#
# Independent of the hardware backstop, software still tracks session_used
# and fires a force-OFF if it crosses 140% of the target. This is the tight
# protection layer for cases where the device's hardware mechanisms succeed
# in delivering water but the software's view of "how much" is correct
# enough to trigger early.
#
# Note: software session_used is consistently UNDER actual delivered volume
# due to the device's 1-decimal m³/h precision. So this guardrail effectively
# fires somewhere between ~140% and ~180% of actual delivered volume,
# depending on flow rate. That's still a useful upper bound.
# ─────────────────────────────────────────────────────────────────────────────

GUARDRAIL_SOFTWARE_OVERSHOOT_RATIO = 1.40  # 140% of target

# After firing the software overshoot guardrail, give the device this many
# seconds to actually close before treating it as a panic-level failure.
GUARDRAIL_SOFTWARE_OVERSHOOT_GRACE_SECONDS = 60

# ─────────────────────────────────────────────────────────────────────────────
# v3.2 — Panic system (catastrophic failure escalation)
#
# When the integration's normal failsafe mechanisms have been exhausted and
# water is still flowing, fire panic events that an external automation can
# use to kill an upstream device (e.g., the main water pump). The integration
# itself does NOT directly control any upstream device — it only emits
# events. v4.0 will add a config field for an entity to turn off directly.
#
# Trip conditions (any one of these is enough):
#   1. The OFF retry chain (5 minutes of escalating retries) has exhausted
#      and the device is still ON.
#   2. Two or more valves are simultaneously in shutoff_in_progress state
#      with retry chains running (indicates broader system failure).
#   3. The software 140% overshoot guardrail fired AND the device is still
#      ON after GUARDRAIL_SOFTWARE_OVERSHOOT_GRACE_SECONDS.
#
# Manual clear via service `z2m_irrigation.clear_panic`.
# Panic state survives HA restart (persisted via restore_state on the
# binary_sensor).
# ─────────────────────────────────────────────────────────────────────────────

# Minimum number of valves in shutoff_in_progress state to trip panic
# condition #2 (multiple-valve failure).
PANIC_MULTIPLE_VALVES_THRESHOLD = 2

EVENT_PANIC_REQUIRED = "z2m_irrigation_panic_required"
EVENT_PANIC_CLEARED = "z2m_irrigation_panic_cleared"

# ─────────────────────────────────────────────────────────────────────────────
# v3.2 — Device status monitoring
#
# The Sonoff SWV exposes `current_device_status` which can be one of:
#   - normal_state
#   - water_shortage
#   - water_leakage
#   - water_shortage & water_leakage
#
# When this transitions away from normal_state, fire an event so external
# automations can alert the user.
# ─────────────────────────────────────────────────────────────────────────────

EVENT_DEVICE_STATUS_CHANGED = "z2m_irrigation_device_status_changed"

# ─────────────────────────────────────────────────────────────────────────────
# v3.2.1 — Initial valve setup
#
# When the integration first sees a valve, push these settings to align the
# device with v3.2.1 expectations.
#
# auto_close_when_water_shortage = DISABLE
#   v3.2 originally tried to ENABLE this as a "free 30-min hardware safety
#   net". v3.2.1 testing on 2026-04-08 revealed that ENABLE breaks
#   cyclic_quantitative_irrigation: when this flag is on, sending an
#   irrigation_capacity command silently fails (the volume target is set
#   in the MQTT payload but the device clears it before counting). With
#   DISABLE, cyclic_quantitative_irrigation works correctly.
#
#   We actively SET DISABLE on every newly-discovered valve to undo any
#   damage from a previous v3.2 install on the same valve.
# ─────────────────────────────────────────────────────────────────────────────

INITIAL_VALVE_AUTO_CLOSE_WHEN_WATER_SHORTAGE = "DISABLE"
