# Changelog

All notable changes to the Z2M Irrigation integration will be documented in this file.

## [3.1.2] - 2026-04-08

### 🐛 Critical hotfix — thread-safety bug bricked the at-target failsafe

Real-world morning irrigation run on 2026-04-08 hit the bug. The smart
irrigation automation triggered Front Garden + Back Garden + Lilly Pilly
runs at sunrise. When Front Garden's volume hit its 324 L target, the
at-target failsafe in `_on_state` fired exactly as designed, set
`shutoff_in_progress = True`, logged the warning, and then **crashed
inside `hass.bus.async_fire(EVENT_SHUTOFF_INITIATED, …)`** with

```
RuntimeError: Detected ... non-thread-safe operation: ...
```

because `_on_state` is the MQTT message callback which runs from a
SyncWorker thread, not the HA event loop. HA's strict mode aborted the
call before the OFF retry chain could be scheduled.

Result: `shutoff_in_progress` was set to `True` (blocking subsequent
re-fires of the failsafe via the gate `if v.state == "ON" and not
v.shutoff_in_progress:`) but **no OFF was ever published to the device**.
Front Garden ran past its target indefinitely. Back Garden hit the same
code path and the same bug, ran ~3× target before manual intervention.

The Layer 1–4 guardrails in `_guardrail_tick` did NOT hit the bug because
that loop is registered via `async_track_time_interval` which always runs
on the event loop thread. The bug was specific to code paths called from
the MQTT worker thread:

| Call site | Thread | Affected? |
|---|---|---|
| `_initiate_shutoff` from `_on_state` (at-target failsafe) | SyncWorker | ❌ broken |
| `_initiate_shutoff` from `_guardrail_tick` (Layers 1-3) | MainThread | ✅ worked |
| State→OFF transition `EVENT_SHUTOFF_CONFIRMED` in `_on_state` | SyncWorker | ❌ broken |
| `_attempt_shutoff` `EVENT_SHUTOFF_FAILED` (via `async_call_later`) | MainThread | ✅ worked |
| `_create_persistent_notification` | depends on caller | ❌ broken when called from worker |
| Orphan recovery `EVENT_ORPHANED_SESSION_RECOVERED` (via `EVENT_HOMEASSISTANT_STARTED`) | MainThread | ✅ worked |

#### Fix

Two new helpers, both safe to call from any thread:

- **`_fire_event(event_type, event_data)`** — wraps `hass.bus.async_fire`
  via `hass.loop.call_soon_threadsafe`
- **`_create_persistent_notification`** — already existed, now wraps the
  whole `hass.async_create_task` + `services.async_call` chain via
  `loop.call_soon_threadsafe`

Every direct `self.hass.bus.async_fire(...)` call in `manager.py` is now
replaced with `self._fire_event(...)`. The in-thread-loop call sites that
weren't actually broken are also converted to use the helper, for
consistency and to prevent future regressions.

#### Files changed

- `custom_components/z2m_irrigation/manager.py` — add `_fire_event` helper,
  replace all 5 `hass.bus.async_fire` call sites, fix `_create_persistent_notification`
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.1.2`

No schema changes, no behaviour changes outside of "the failsafe now
actually fires". The 5 guardrails, OFF retry chain, and at-target failsafe
are otherwise identical to v3.1.1.

#### Note on data loss during this incident

The morning run lost an estimated ~600-1000 L of water across Front Garden
and Back Garden before manual `mqtt.publish` OFF intervention at 10:24
AEST. Lilly Pilly was unaffected by this bug (its session never reached
the at-target failsafe path) but had a separate physical flow blockage
that prevented water from reaching the plants — investigated separately.

---

## [3.1.1] - 2026-04-07

### 🐛 Hotfix — orphan recovery: defer side-effects until HA fully started

Real-world deployment of v3.1.0 against a production HA box found two related
bugs in `_recover_orphaned_sessions()`. Both have the same root cause and
both are fixed here.

#### What was wrong

`_recover_orphaned_sessions()` runs during `async_start()`, which executes
while Home Assistant is still in `CoreState.starting`. At that point:

- The MQTT integration is loaded but its **client may not be connected yet**
  — `mqtt.async_publish()` raises "The client is not currently connected".
- The `persistent_notification` integration may not have registered its
  service yet — `services.async_call("persistent_notification", "create", …)`
  silently no-ops.

The first deployment of v3.1.0 detected 91 legitimate orphan sessions
(accumulated from months of HA restarts before the fix existed) and:

- ✅ Successfully closed all 91 in the local SQLite DB.
- ❌ All 91 force-OFF MQTT publishes failed with "client not connected".
- ❌ The user-facing persistent notification was never created.

No real-world harm because the valves were physically OFF anyway, but the
**primary safety mechanism (force-OFF on restart) wasn't actually firing**
when it was needed most.

#### Fix — two-phase recovery

`_recover_orphaned_sessions()` is now split:

| Phase | When | What |
|---|---|---|
| **1 — DB cleanup** | `async_start()` (immediately) | Marks all orphan sessions as ended in the local SQLite DB. Pure local op, no external dependencies. |
| **2 — Force-OFF + notification** | `EVENT_HOMEASSISTANT_STARTED` (deferred) | Dedupe orphans by valve_topic, publish OFF once per unique valve via MQTT, fire one event per valve, create one summary persistent notification. |

The Phase 2 callback is registered via `hass.bus.async_listen_once()` for
the normal boot path, OR scheduled immediately if HA is already running
(config-reload edge case).

#### Bonus fix — dedupe orphans by valve_topic

The first v3.1.0 run logged ~91 OFF publishes for only 4 unique valves
(Front Garden alone had ~30 orphan sessions, mostly from past restarts).
Now we publish OFF **once per unique valve**, regardless of how many orphan
sessions belonged to it.

Persistent notification is also smarter: it shows up to 5 valve names
inline, then "and N more" for larger counts.

#### Files changed

- `custom_components/z2m_irrigation/manager.py` — split recovery into two
  phases; new imports for `CoreState` and `EVENT_HOMEASSISTANT_STARTED`.
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.1.1`.

No schema changes. No new constants. No new behaviour outside the recovery
path. The 5 guardrails, OFF retry chain, and at-target failsafe from v3.1.0
are unchanged.

---

## [3.1.0] - 2026-04-07

### 🛡️ Safety release — multi-layered failsafe, OFF retry, restart recovery

This is a **safety-critical** release. The previous control loop had several
failure modes that could leave a valve running unbounded — see
[`AUDIT-2026-04-07.md`](./AUDIT-2026-04-07.md) for the full pre-fix audit.

All changes are surgical and contained to `manager.py`, `database.py`,
`const.py`, and the manifest. **No schema changes** to the SQLite database;
the new safety paths reuse the existing `sessions` table's `ended_at IS NULL`
semantics to identify in-flight sessions.

#### 🐛 Bugs fixed

- **CRITICAL — Volume target lost on HA restart.** Previously, if HA was
  restarted while a valve was physically open, the next MQTT `state: ON` from
  the device created a new in-memory session with `target_liters=None`, and
  the failsafe never fired. The valve could run unbounded until manual
  intervention.
- **CRITICAL — Runaway after primary failsafe.** Previously, when the at-target
  failsafe fired, it published OFF once with no retry, and immediately cleared
  `target_liters`. If the device failed to actually close (lost MQTT command,
  Zigbee delivery failure, firmware quirk), `session_liters` kept climbing
  indefinitely with no further failsafe — consistent with the user-reported
  "800 L target → 2000–3000 L actual" runaway.
- **CRITICAL — No MQTT-independent failsafe.** Previously, the at-target check
  ran ONLY inside `_on_state` (the MQTT message handler). If the device went
  silent (Zigbee dropout, dead battery), the failsafe never fired regardless
  of how much time had elapsed.
- **HIGH — No retry / verification of OFF.** Previously, OFF was published
  once with QoS 1 (broker-delivery only), with no acknowledgement check and
  no retry.

#### ✨ New: 5-layer safety guardrail loop

A new periodic loop runs every `GUARDRAIL_CHECK_INTERVAL_SECONDS` (30s) and
inspects every active session, completely independently of MQTT messages:

| Layer | What it catches | Default threshold |
|---|---|---|
| **1 — Volume overshoot** | Primary failsafe sent OFF but device kept flowing past target | `> target × 1.25` |
| **2 — Stuck flow** | Valve never opened, or flow sensor broken / reporting zero | `> 10 min` with no liter progress |
| **3 — MQTT silence** | Device went offline mid-run (Zigbee dropout, dead battery) | `> 5 min` since last MQTT msg |
| **4 — Expected duration warning** *(informational)* | Run is taking 50% longer than the historical average — possible clogged filter or pressure drop | `> historical_avg × 1.5` |
| **5 — Cross-restart recovery** | HA restarted mid-irrigation; orphaned session in DB | At every startup |

Layers 1–3 trigger the new shutoff retry chain. Layer 4 is informational only
(logs a warning + fires a HA event but does NOT force OFF). Layer 5 runs once
at startup, force-publishes OFF to all valves with orphaned in-flight
sessions, marks the sessions as completed in the DB, and creates a persistent
notification for the user.

All thresholds live in `const.py` and can be tuned without code changes.

#### ✨ New: OFF retry / confirmation state machine

When ANY guardrail (or the primary at-target failsafe) decides a valve must
shut off, the new `_initiate_shutoff()` / `_attempt_shutoff()` chain takes
ownership of the valve until the device confirms `state: OFF` or the retry
budget is exhausted. Schedule:

| Elapsed | Action |
|---|---|
| `T+0s` | Publish OFF (attempt 1) |
| `T+3s` | If still ON, publish OFF (attempt 2) |
| `T+8s` | If still ON, publish OFF (attempt 3) |
| `T+15s` | If still ON, publish OFF (attempt 4) — log WARNING |
| `T+30s` | If still ON, publish OFF (attempt 5) — **persistent notification** |
| `T+60s` → `T+300s` | Periodic retries |
| `T+300s` | Give up — fire `z2m_irrigation_shutoff_failed` event + **CRITICAL persistent notification** |

When the device finally reports `state: OFF`, the `EVENT_SHUTOFF_CONFIRMED`
event fires and the chain cleanly tears down. Idempotent: a second
`_initiate_shutoff` call while one is already in progress is silently ignored.

#### ✨ New: HA bus events for automation hooks

Three new HA events are fired so users can hook them in automations
(notifications, escalation, dashboards, etc.):

- `z2m_irrigation_shutoff_initiated` — fired when any guardrail/failsafe decides to OFF a valve
- `z2m_irrigation_shutoff_confirmed` — fired when the device finally confirms OFF
- `z2m_irrigation_shutoff_failed` — fired only after the entire 5-minute retry budget is exhausted
- `z2m_irrigation_orphaned_session_recovered` — fired at startup for each orphaned session found

#### ✨ New: Database method `get_in_flight_sessions()`

Added to `database.py` to support startup recovery. No schema changes — uses
the existing `WHERE ended_at IS NULL` query against the `sessions` table.

Also added `get_recent_avg_flow()` to support Layer 4 (expected duration
warning) — queries the last N completed sessions for a valve.

#### 🚧 Known issue (will be addressed in 3.1.1)

The duplicate session-end log line observed when manually toggling a valve
off (`Session ending ... 0.00min, 0.00L, 1.67lpm`) is a separate state-flap
issue — the device briefly toggles `state: ON → OFF → ON → OFF` in response
to the OFF command, which creates a second 60ms-long phantom session in the
DB. Cosmetic only, not a safety issue. Tracked separately.

#### 🛠️ Other changes

- `start_timed()` failsafe backup timer now also routes through the new
  retry chain instead of publishing OFF once.
- Added `recovered_from_orphan` field on `Valve` (currently used for log
  labelling only).
- All new constants are in `const.py` for easy tuning.
- Added [`AUDIT-2026-04-07.md`](./AUDIT-2026-04-07.md) — the full pre-fix
  audit and bug analysis.

---

## [3.0.6] - 2025-11-05

### 🐛 Critical Fix - Timezone Required for Last Session Start

#### Fixed Timezone-Aware Datetime
- **FIXED: Last Session Start timezone error** - Sensor now properly handles timezone-aware datetimes
  - **Error**: `ValueError: Invalid datetime: sensor provides state '2025-11-05 09:10:44.203866', which is missing timezone information`
  - **Problem**: Home Assistant timestamp sensors REQUIRE timezone-aware datetime objects
  - **Solution**: Added UTC timezone to parsed datetime objects
  - Imported `timezone` from datetime module
  - Check if datetime is naive (no timezone) and add UTC timezone
  - All timestamps now properly display with correct timezone info

---

## [3.0.5] - 2025-11-05

### 🐛 Bug Fix - Last Session Start Sensor

#### Fixed Timestamp Display
- **FIXED: Last Session Start showing "Unknown"** - Sensor now properly displays timestamp
  - **Problem**: Home Assistant's timestamp device class requires datetime object, not ISO string
  - **Error**: Sensor was throwing exception when updating, causing "Unknown" display
  - **Solution**: Parse ISO datetime string to Python datetime object in native_value property
  - Handles missing data gracefully (returns None)
  - Includes error handling for malformed dates

---

## [3.0.4] - 2025-11-05

### ✨ New Sensor - Last Session Start

#### Last Session Start Datetime
- **NEW: Last Session Start sensor** - Shows the start datetime of the most recent completed session
  - Displays as a timestamp in Home Assistant
  - Updates automatically when session ends
  - Also updates during periodic 15-minute refresh
  - Useful for tracking when irrigation last ran
  - Stored in database, persists across restarts
  - Returns `None` if no sessions recorded yet

---

## [3.0.3] - 2025-11-05

### ✨ Enhancement - Automatic Time-Based Sensor Updates

#### Periodic Refresh for 24h/7d Sensors
- **NEW: Automatic periodic refresh** - 24h and 7d sensors now update automatically every 15 minutes
  - **Problem**: Sensors only updated when valve was triggered, causing stale data
  - **Example**: Old sessions would remain counted past 24h until next valve use
  - **Solution**: Added periodic background refresh every 15 minutes
  - Sensors now stay accurate without requiring manual valve triggering
  - Uses Home Assistant's `async_track_time_interval` for reliable scheduling

---

## [3.0.2] - 2025-11-04

### 🐛 Critical Bug Fix - Time-Based Sensors

#### 24h/7d Calculation Fix
- **CRITICAL FIX: 24h and 7d sensors showing incorrect values** - Fixed database queries for time-based metrics:
  - **Problem**: Queries were using `started_at >= cutoff` which only counted sessions that *started* within the time window
  - **Result**: Sensors were showing cumulative totals instead of rolling time windows
  - **Solution**: Changed to `ended_at >= cutoff` to correctly count sessions that *completed* within the time window
  - Both 24h and 7d sensors now accurately show rolling window usage

---

## [3.0.1] - 2025-11-02

### 🐛 Critical Bug Fixes

#### Race Condition Fixes
- **CRITICAL FIX: Session tracking race conditions** - Fixed multiple race conditions:
  1. **Session ID capture bug**: Session IDs were being cleared before async database operations completed, resulting in `session_id=None` in logs and NULL `ended_at` in database. Now captures all session values before clearing them.
  2. **Sensor initialization race**: Sensors were showing `0.0` on restart because they were created before valve data loaded from database. Now loads all metrics BEFORE announcing valve to sensor platform.

---

## [3.0.0] - 2025-11-01

### 🎉 MAJOR RELEASE - 100% Local Persistence

#### Bug Fixes (Nov 1, 2025)
- **CRITICAL FIX: Session tracking race conditions** - Fixed multiple race conditions:
  1. **Session ID capture bug**: Session IDs were being cleared before async database operations completed, resulting in `session_id=None` in logs and NULL `ended_at` in database. Now captures all session values before clearing them.
  2. **Sensor initialization race**: Sensors were showing `0.0` on restart because they were created before valve data loaded from database. Now loads all metrics BEFORE announcing valve to sensor platform.
- **CRITICAL FIX: Sessions not ending properly** - Fixed race condition where `current_session_id` was set AFTER async database save, causing sessions to not be recorded if valve turned off quickly. Now generates session_id immediately when valve turns ON.
- Fixed MQTT connection timing issue on startup (graceful handling if MQTT not ready)
- Fixed `async_add_entities` RuntimeError by adding @callback decorator to entity addition functions
- Fixed missing `_LOGGER` import in `__init__.py`
- Fixed SQLite concurrent access issues by enabling WAL mode
- Fixed SQLite query handling for NULL results in 24h/7d usage calculations - added explicit None checks before float conversion
- **Fixed SQLite "bad parameter or other API misuse" errors** by:
  - Using `connection.execute()` directly instead of creating cursors (better thread safety in Home Assistant's executor)
  - Adding explicit string conversion for all parameters
  - Adding parameter validation and type checking
  - **Added threading.Lock to protect all database operations** - prevents race conditions in Home Assistant's executor thread pool
- **Added COMPLETE debug logging** - Every database operation, manager action, and session tracked with ➡️/⬅️ arrows (see DEBUGGING-24H-7D.md)
- Integration now loads successfully even if MQTT connects after integration startup

#### Breaking Changes
- **Removed Supabase cloud dependency** - All data now stored locally in SQLite
- **Scheduler temporarily disabled** - Smart schedules require database migration (coming in v3.1.0)
  - Manual watering via services (`start_liters`, `start_timed`) works perfectly
  - Use automations for scheduling in the meantime
- No more .env file needed
- No more external configuration
- Fully local, no internet required

#### New Features

**Local SQLite Database**
- All irrigation data stored in `/config/z2m_irrigation.db`
- Automatic initialization on startup
- Survives all Home Assistant restarts
- Auto-cleanup of old sessions (>90 days)
- Included in Home Assistant backups automatically

**4 New Time-Based Sensors Per Valve**
- `sensor.xxx_last_24h` - Liters used in last 24 hours
- `sensor.xxx_last_24h_minutes` - Runtime in last 24 hours
- `sensor.xxx_last_7_days` - Liters used in last 7 days
- `sensor.xxx_last_7_days_minutes` - Runtime in last 7 days

**Universal Session Tracking**
- Tracks ALL valve usage regardless of trigger source:
  - Integration service calls
  - Manual switch toggles
  - Automations
  - Z2M manual control
  - Physical valve button
- Rolling time windows (24h, 7d) update after every session
- Complete history preserved

#### Improvements
- Faster startup (no external API calls)
- Better reliability (no network dependency)
- Simpler setup (no cloud configuration)
- Enhanced debug logging with emojis
- Better performance with indexed queries

#### Migration
- Existing data from v2.x not migrated (fresh start)
- All sensors remain compatible
- No configuration changes needed
- Just restart Home Assistant!

See `LOCAL-PERSISTENCE-GUIDE.md` for complete documentation.

---

## [2.0.0] - 2025-10-20

### 🎉 MAJOR RELEASE - Smart Scheduling System

#### New Features: Irrigation Scheduling

**Time-Based Schedules**
- Create schedules that run at specific times (e.g., 6:00 AM, 6:00 PM)
- Select specific days of the week or run daily
- Set duration (minutes) or volume (liters) targets
- Enable/disable schedules without deleting them

**Interval-Based Schedules**
- Run valves every X hours automatically
- Perfect for frequent watering needs
- Tracks last run time automatically

**Smart Conditions (Weather-Aware)**
- Skip if soil moisture is too high (sensor integration)
- Skip based on temperature ranges (weather integration)
- Skip if it rained recently (weather integration)
- Conditions are optional - simple schedules work too!

**Database Backend**
- All schedules stored in Supabase
- Schedule run history tracked automatically
- View why schedules were skipped (conditions, manual, etc.)
- Link schedule runs to irrigation sessions

#### New Services

- `z2m_irrigation.create_schedule` - Create new schedule
- `z2m_irrigation.update_schedule` - Modify existing schedule
- `z2m_irrigation.delete_schedule` - Remove schedule
- `z2m_irrigation.enable_schedule` - Enable schedule
- `z2m_irrigation.disable_schedule` - Disable schedule
- `z2m_irrigation.run_schedule_now` - Trigger schedule immediately
- `z2m_irrigation.reload_schedules` - Reload from database

#### WebSocket API

- `z2m_irrigation/schedules/list` - Get all schedules
- `z2m_irrigation/schedules/get` - Get specific schedule
- `z2m_irrigation/schedules/runs` - Get schedule run history

#### Architecture Changes

- New `scheduler.py` module handles all scheduling logic
- Checks for due schedules every minute
- Automatic next-run-time calculation
- Priority system for overlapping schedules
- Thread-safe execution

**Breaking Changes:**
- `hass.data[DOMAIN][entry_id]` now returns `{"manager": ..., "scheduler": ...}` instead of just the manager

---

## [1.0.3] - 2025-10-20

### 🚨 CRITICAL - Threading Fixes

#### Thread Safety Violations Fixed
- **FIXED**: All threading violations causing Home Assistant crashes
  - Added `_schedule_task()` helper for thread-safe async task scheduling
  - Fixed `_on_state()` MQTT callback to use `call_soon_threadsafe()`
  - Added `@callback` decorator to all entity update callbacks
  - Entities (sensor/switch/number) now update safely from dispatcher signals

#### Failsafes Now Actually Work
- **CONFIRMED**: Failsafes detected 12L/5L overflow and tried to stop valve
  - Previous threading errors prevented OFF command from executing
  - Now properly sends OFF command when targets exceeded
  - Uses thread-safe task scheduling

**Critical upgrade**: v1.0.2 had the logic but threading bugs prevented execution. v1.0.3 actually works!

---

## [1.0.2] - 2025-10-20

### 🐛 Critical Fixes - Device Quirk Discovered

#### Device Clears Native Volume Commands
- **DISCOVERED**: Sonoff SWV clears `cyclic_quantitative_irrigation` immediately after starting
  - Z2M logs show: device accepts command, sets `current_count:1`, valve turns ON
  - Then immediately: `irrigation_capacity:0, total_number:0` (program cleared!)
  - **Solution**: Use simple ON/OFF + HA monitoring for volume runs
  - Timed runs: Testing needed to see if `cyclic_timed_irrigation` has same issue

#### Failsafe System Fixes
- **FIXED**: Failsafes now check on EVERY MQTT update, not just during flow integration
  - Volume failsafe now triggers even if flow stops or is zero
  - Time failsafe now checks anytime valve is ON with a target time
  - Added progress logging (DEBUG level) to track volume runs
  - Failsafes clear targets after triggering to prevent repeated OFF commands

#### Switch State Delay
- **DOCUMENTED**: Switch entity updates when Z2M publishes state, not instantly
  - This is normal Zigbee behavior (device → coordinator → Z2M → MQTT → HA)
  - Typical delay: 1-3 seconds
  - State eventually syncs correctly

---

## [1.0.1] - 2025-10-20

### 🐛 Critical Fixes

#### Volume-Based Runs Not Stopping
- **FIXED**: Added automatic valve shutoff when target liters reached
  - Integration now actively monitors flow and turns off valve when target is reached
  - Prevents overwatering that was occurring in v1.0.0
  - Added detailed logging when volume target is reached

#### Native Device Commands Fixed
- **CORRECTED**: Now using proper `cyclic_quantitative_irrigation` and `cyclic_timed_irrigation` objects
  - Previous attempts used wrong parameters: `water_consumed`, `timer` (not supported)
  - Now using correct Z2M API per device documentation
  - Device will handle shutoff natively + HA backup monitoring as failsafe

#### Flow Conversion Clarified
- **DOCUMENTED**: Device reports flow in m³/h, not L/min
  - Conversion: 1 m³/h = 16.667 L/min
  - `flow_scale` is a user multiplier (default 1.0)

### Technical Details

**What Was Wrong:**
- Using `{"state": "ON", "water_consumed": 6000}` ❌ (Z2M: "No converter available")
- Using `{"state": "ON", "timer": 360}` ❌ (Z2M: "No converter available")

**What's Correct:**
- Volume: `{"cyclic_quantitative_irrigation": {"current_count": 0, "total_number": 1, "irrigation_capacity": 6, "irrigation_interval": 0}}` ✅
- Timed: `{"cyclic_timed_irrigation": {"current_count": 0, "total_number": 1, "irrigation_duration": 360, "irrigation_interval": 0}}` ✅

### How It Works Now - Triple Failsafe System

**Volume Runs (3 layers of protection):**
1. **Native Device Control**: `cyclic_quantitative_irrigation` command tells device to stop at target
2. **Real-time Monitoring**: HA checks every MQTT update if `session_liters >= target_liters`
3. **Forced Shutoff**: If target exceeded, HA sends OFF command immediately (logged as WARNING)

**Timed Runs (3 layers of protection):**
1. **Native Device Control**: `cyclic_timed_irrigation` command tells device to stop at target time
2. **Real-time Monitoring**: HA checks every MQTT update if `now >= session_end_ts`
3. **Backup Timer**: HA timer fires at exact target time and forces OFF if still running (logged as WARNING)

**Result**: Even if the device completely fails, HA will ALWAYS turn off the valve when targets are reached.

**⚠️ Upgrade immediately if using volume-based irrigation!**

---

## [1.0.0] - 2025-10-20

### 🎉 Major Release

Complete rewrite with enhanced features and local database integration.

### ✨ Added

- **Session Duration Sensor** - Track how long the current irrigation session has been running
- **Dual Remaining Sensors** - Separate sensors for remaining time and remaining liters with smart estimates
- **Native Zigbee Control** - Commands sent directly to device for offline operation
  - Timed runs use device's built-in timer
  - Volume runs use device's built-in water meter
- **Local Database Integration** - Session history stored in Home Assistant's recorder (no cloud required)
- **Battery Level Sensor** - Monitor valve battery status
- **Link Quality Sensor** - Track Zigbee signal strength
- **Session Count Sensor** - Total number of irrigation sessions
- **Number Entities** - Easy-to-use controls for setting run duration and volume
- **Enhanced Documentation** - Comprehensive README and installation guide

### 🔧 Changed

- **Unit Conversion Fixed** - Properly converts m³/h to L/min (multiply by 16.667)
- **Flow Rate Accuracy** - Corrected flow rate calculations for Sonoff SWV devices
- **Threading Issues Resolved** - Fixed all async/await patterns to prevent event loop errors
- **Session Tracking Improved** - Better session start/end detection and logging
- **Reset Service Enhanced** - Now also resets session count

### 🗑️ Removed

- **Supabase Dependency** - Replaced with native Home Assistant database
- **Cloud Dependencies** - All data stored locally
- **Unnecessary Files** - Cleaned up non-integration files from repository

### 📊 Technical Improvements

- Home Assistant recorder integration for long-term statistics
- Proper async/await patterns throughout codebase
- Better error handling and logging
- Optimized MQTT message processing
- Improved device discovery reliability

### 📚 Documentation

- Complete README with features, installation, and troubleshooting
- Detailed installation guide with HACS and manual methods
- Service examples and usage patterns
- Dashboard customization examples
- Troubleshooting section with common issues

---

## [0.9.2] - Previous Version

### Features

- Basic valve control via MQTT
- Flow rate monitoring
- Session tracking
- Total usage counters
- Timed run support
- Volume run support

---

## Migration from 0.9.x to 1.0.0

### Breaking Changes

None - this version is fully backward compatible!

### What You Get

After upgrading, you'll see these new entities per valve:
- `sensor.{valve}_session_duration`
- `sensor.{valve}_remaining_time`
- `sensor.{valve}_remaining_liters`
- `sensor.{valve}_battery`
- `sensor.{valve}_link_quality`
- `sensor.{valve}_session_count`
- `number.{valve}_run_for_minutes`
- `number.{valve}_run_for_liters`

Old entities remain unchanged:
- `switch.{valve}_valve`
- `sensor.{valve}_flow`
- `sensor.{valve}_session_used`
- `sensor.{valve}_total`
- `sensor.{valve}_total_minutes`

### Upgrade Steps

1. Update via HACS or replace files manually
2. Restart Home Assistant
3. All new sensors will appear automatically
4. Update your dashboards to include new entities
5. Session history starts logging immediately

---

**Note**: This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.
