# Changelog

All notable changes to the Z2M Irrigation integration will be documented in this file.

## [3.0.0] - 2025-11-01

### 🎉 MAJOR RELEASE - 100% Local Persistence

#### Bug Fixes (Latest)
- Fixed MQTT connection timing issue on startup (graceful handling if MQTT not ready)
- Fixed `async_add_entities` TypeError (removed incorrect await statements)
- Fixed missing `_LOGGER` import in `__init__.py`
- Fixed SQLite concurrent access issues by enabling WAL mode
- Fixed SQLite cursor management - all cursors now properly closed after use
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
