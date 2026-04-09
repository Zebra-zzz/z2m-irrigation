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

# v4.0-alpha-1 — global dispatcher signal fired by the manager whenever
# any system-wide state changes that the global sensors should react to
# (today_calculation refreshed, master_enable toggled, zone config edited).
# Per-valve updates continue to use sig_update(topic) — global sensors that
# care about per-valve state subscribe to those individually via SIG_NEW_VALVE.
SIG_GLOBAL_UPDATE = "z2m_irrigation_global_update"

def sig_zone_config_changed(zone: str) -> str:
    return f"z2m_irrigation_zone_config_changed::{zone}"

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

# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-1 — JSON config store
#
# Per Stage 2 architecture: the integration owns two persistence stores.
#   1. SQLite session-history database (`database.py`) — append-mostly
#      time-series of valve sessions.
#   2. JSON config store (`zone_store.py`) — small mutable config (zones,
#      schedules, history events). Stored in HA's `.storage/` dir via the
#      `homeassistant.helpers.storage.Store` helper.
#
# The store key is suffixed with the config_entry_id so two instances of
# the integration would not collide.
# ─────────────────────────────────────────────────────────────────────────────

STORE_VERSION = 1
STORE_KEY_PREFIX = "z2m_irrigation"

# Per-zone defaults applied when a valve is first discovered. The user can
# edit any of these per-zone via the Setup tab in v4.0 / via service calls.
DEFAULT_ZONE_FACTOR = 1.0
DEFAULT_ZONE_L_PER_MM = 12.0
DEFAULT_ZONE_BASE_MM = 4.0
DEFAULT_ZONE_IN_SMART_CYCLE = True

# Persistence retention for the per-zone run history. Older entries are
# pruned on each write to keep the JSON store small. Both a date cutoff
# AND a hard count cap apply — whichever is more aggressive wins.
HISTORY_RETENTION_DAYS = 90

# Hard cap on history entries per scope (e.g. global schedule timeline,
# per-zone session summaries). Prevents unbounded JSON growth even on
# unusual usage patterns. ~500 entries × ~200 bytes ≈ 100 KB per scope.
HISTORY_MAX_ENTRIES = 500

# Lookback used by the rolling avg-flow per-zone sensor. Reads from the
# existing SQLite session history via `db.get_recent_avg_flow`. Higher
# values smooth out one-off anomalies; lower values react faster to
# changing conditions (filter clog, valve degradation).
AVG_FLOW_LOOKBACK_DAYS = 7
AVG_FLOW_LOOKBACK_SESSIONS = 10

# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-1 — config flow keys
# ─────────────────────────────────────────────────────────────────────────────

# Step 2 — weather sources (all optional, calculator falls back gracefully)
CONF_WEATHER_VPD_ENTITY = "weather_vpd_entity"
CONF_WEATHER_RAIN_TODAY_ENTITY = "weather_rain_today_entity"
CONF_WEATHER_RAIN_FORECAST_24H_ENTITY = "weather_rain_forecast_24h_entity"
CONF_WEATHER_TEMP_ENTITY = "weather_temp_entity"

# Step 3 — safety + global thresholds
CONF_KILL_SWITCH_ENTITY = "kill_switch_entity"
CONF_KILL_SWITCH_MODE = "kill_switch_mode"
CONF_GLOBAL_SKIP_RAIN_MM = "global_skip_rain_threshold_mm"
CONF_GLOBAL_SKIP_FORECAST_MM = "global_skip_forecast_threshold_mm"
CONF_GLOBAL_MIN_RUN_LITERS = "global_min_run_liters"

KILL_SWITCH_MODE_OFF_ONLY = "off_only"
KILL_SWITCH_MODE_OFF_AND_NOTIFY = "off_and_notify"
KILL_SWITCH_MODE_DISABLED = "disabled"
KILL_SWITCH_MODES = [
    KILL_SWITCH_MODE_OFF_ONLY,
    KILL_SWITCH_MODE_OFF_AND_NOTIFY,
    KILL_SWITCH_MODE_DISABLED,
]
DEFAULT_KILL_SWITCH_MODE = KILL_SWITCH_MODE_OFF_AND_NOTIFY

DEFAULT_GLOBAL_SKIP_RAIN_MM = 5.0
DEFAULT_GLOBAL_SKIP_FORECAST_MM = 8.0
DEFAULT_GLOBAL_MIN_RUN_LITERS = 2.0

# ─────────────────────────────────────────────────────────────────────────────
# v4.0-alpha-2 — Scheduler engine
# ─────────────────────────────────────────────────────────────────────────────

# Stage 2 schedule modes:
#   smart — calculator chooses per-zone liters from current weather + zone cfg
#   fixed — every zone in the schedule gets the same fixed_liters_per_zone
SCHEDULE_MODE_SMART = "smart"
SCHEDULE_MODE_FIXED = "fixed"
SCHEDULE_MODES = [SCHEDULE_MODE_SMART, SCHEDULE_MODE_FIXED]

# Weekday tokens — match Stage 2 spec. Index = Python weekday (Mon=0..Sun=6).
DAYS_OF_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Catch-up window: if HA starts up and missed a schedule's fire time by no
# more than this many minutes, run it now. Beyond this, the missed run is
# logged as `skipped_catchup_window` and the user can manually re-trigger.
SCHEDULE_CATCHUP_WINDOW_MINUTES = 30

# Time the engine waits between sequential zones in a multi-zone schedule.
# Gives the device a moment to fully close before the next opens.
SCHEDULE_INTER_ZONE_GAP_SECONDS = 5

# Maximum time the engine waits for a published volume run to actually
# transition the valve to session_active. If the device doesn't acknowledge
# within this window the engine logs a warning and advances to the next
# queue entry rather than getting wedged.
SCHEDULE_RUN_START_TIMEOUT_SECONDS = 60

# Polling cadence for the queue runner's "is the active valve still
# running?" check. Cheap — just an in-memory bool read.
SCHEDULE_QUEUE_POLL_SECONDS = 2

# Schedule outcome labels written to the schedule's `last_run_outcome`
# field after each fire attempt. Surfaced on the dashboard schedule list.
OUTCOME_RAN = "ran"
OUTCOME_RAN_PARTIAL = "ran_partial"
OUTCOME_SKIPPED_RAIN = "skipped_rain"
OUTCOME_SKIPPED_FORECAST = "skipped_forecast"
OUTCOME_SKIPPED_DISABLED = "skipped_disabled"
OUTCOME_SKIPPED_PAUSED = "skipped_master_paused"
OUTCOME_SKIPPED_PANIC = "skipped_panic"
OUTCOME_SKIPPED_TODAY = "skipped_today"
OUTCOME_SKIPPED_NO_ZONES = "skipped_no_zones"
OUTCOME_SKIPPED_CATCHUP_WINDOW = "skipped_catchup_window"
OUTCOME_ERROR = "error"

# Bus event names emitted by the engine for automation hooks.
EVENT_SCHEDULE_FIRED = "z2m_irrigation_schedule_fired"
EVENT_SCHEDULE_SKIPPED = "z2m_irrigation_schedule_skipped"
EVENT_SMART_RUN_STARTED = "z2m_irrigation_smart_run_started"

