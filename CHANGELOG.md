# Changelog

All notable changes to the Z2M Irrigation integration will be documented in this file.

## [1.0.1] - 2025-10-20

### 🐛 Critical Fix

- **FIXED: Volume-based runs not stopping** - Added automatic valve shutoff when target liters reached
  - Integration now actively monitors flow and turns off valve when target is reached
  - Prevents overwatering that was occurring in v1.0.0
  - Added detailed logging when volume target is reached
  - Fallback to simple ON command if device doesn't support native volume control

### What Happened in v1.0.0

The integration was sending a volume command to the device but:
1. The Sonoff SWV may not support the `water_consumed` parameter
2. Even if supported, there was no Home Assistant-side monitoring
3. Result: Valve stayed on indefinitely

### How It Works Now

1. Integration turns valve ON
2. Continuously monitors flow rate and calculates liters used
3. When `session_liters >= target_liters`, automatically sends OFF command
4. Logs when target is reached for debugging

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
