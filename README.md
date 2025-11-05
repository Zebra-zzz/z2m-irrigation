# Z2M Irrigation Controller v3.0.6

**100% Local Smart Irrigation System for Home Assistant** ✅ Complete Tracking

> **Latest Update (Nov 5, 2025):** Fixed Last Session Start sensor timezone issue - now displays correctly with proper timezone information

Control Zigbee2MQTT irrigation valves (Sonoff, GiEX, etc.) with complete local persistence, time-based tracking, and zero cloud dependencies.

---

## ✨ Features

### Core Irrigation (All Working!)
- ✅ **Automatic valve discovery** via MQTT
- ✅ **Flow monitoring** with live L/min tracking
- ✅ **Smart watering** by liters or minutes
- ✅ **Session tracking** - every irrigation session logged
- ✅ **Lifetime totals** - never reset, tracks forever
- ✅ **Resettable totals** - reset anytime for billing periods
- ✅ **100% local persistence** - SQLite database
- ✅ **Universal tracking** - monitors all valve activity regardless of trigger source

### NEW in v3.0.0: Time-Based Tracking ⭐
- 📊 **Last 24 hours** - liters & runtime
- 📊 **Last 7 days** - liters & runtime
- 📊 **Rolling windows** - auto-update after every session
- 📊 **Perfect for alerts** - high usage detection
- 📊 **Weekly reports** - automated summaries

### 17 Sensors Per Valve
- Real-time: flow, session used, session duration, remaining time/liters
- Resettable: total liters, total minutes, session count
- Lifetime: total liters, total minutes, session count
- **NEW:** Last 24h liters, last 24h minutes, last 7d liters, last 7d minutes
- Device: battery level, Zigbee link quality

### Services
- `z2m_irrigation.start_liters` - Water by volume
- `z2m_irrigation.start_timed` - Water by duration
- `z2m_irrigation.reset_totals` - Reset resettable totals (lifetime preserved)
- `z2m_irrigation.rescan` - Re-discover valves

---

## 🚀 Quick Start

### 1. Installation
Copy `custom_components/z2m_irrigation` to your Home Assistant config folder and restart.

### 2. Configuration
1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Z2M Irrigation"**
3. Configure base topic (default: `zigbee2mqtt`)

### 3. That's It!
- ✅ Valves auto-discovered
- ✅ Database created at `/config/z2m_irrigation.db`
- ✅ All sensors created
- ✅ Ready to water!

---

## 💧 Usage Examples

### Water by Volume
```yaml
service: z2m_irrigation.start_liters
data:
  valve: "Front Garden"
  liters: 50
```

### Automation - Daily Watering
```yaml
automation:
  - alias: "Water Front Garden Daily"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: z2m_irrigation.start_liters
        data:
          valve: "Front Garden"
          liters: 50
```

### Alert - High Usage
```yaml
automation:
  - alias: "Alert: High Daily Usage"
    trigger:
      - platform: numeric_state
        entity_id: sensor.water_valve_1_last_24h
        above: 100
    action:
      - service: notify.mobile_app
        data:
          message: "High water usage: {{ trigger.to_state.state }}L in 24h"
```

---

## 📊 Dashboard Example

```yaml
type: entities
title: Irrigation
entities:
  - entity: sensor.water_valve_1_flow
    name: Flow Rate
  - entity: sensor.water_valve_1_last_24h
    name: Last 24 Hours
  - entity: sensor.water_valve_1_last_7_days
    name: Last Week
  - entity: sensor.water_valve_1_lifetime_total
    name: Lifetime Total
```

---

## 🗄️ Database & Persistence

### Local SQLite
- **Location:** `/config/z2m_irrigation.db`
- **Backup:** Included in HA backups automatically
- **No cloud:** 100% local, no internet required

### What's Stored
- All irrigation sessions (start, end, duration, volume)
- Lifetime totals (never reset)
- Resettable totals (manual reset)
- Time-based metrics (24h, 7d rolling windows)

---

## 📋 Logging

Add to `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.z2m_irrigation: debug
```

View logs:
```
Settings → System → Logs → Dropdown → "custom_components.z2m_irrigation"
```

See `LOGGING-SETUP.md` for complete guide.

---

## 📚 Documentation

- **`V3-SUMMARY.md`** - Complete overview
- **`LOCAL-PERSISTENCE-GUIDE.md`** - Database details & examples
- **`LOGGING-SETUP.md`** - Logging configuration
- **`SCHEDULER-STATUS.md`** - Scheduler information
- **`TROUBLESHOOTING.md`** - Common issues
- **`CHANGELOG.md`** - Version history

---

## ⏸️ Scheduler Status

Built-in scheduler **temporarily disabled** in v3.0.0 pending local database migration.

**Workaround:** Use Home Assistant automations (see examples above)

**Coming:** v3.1.0 with full local scheduler

See `SCHEDULER-STATUS.md` for details.

---

## 🎯 What's New in v3.0.0

### Added
- ✅ 100% local SQLite persistence
- ✅ 4 time-based sensors per valve (24h, 7d)
- ✅ Universal session tracking
- ✅ Auto-cleanup of old sessions
- ✅ Emoji-decorated debug logs

### Removed
- ❌ Supabase cloud dependency
- ❌ .env file requirement
- ❌ Internet dependency
- ⏸️ Scheduler (temporarily - use automations)

---

## 🆘 Troubleshooting

### Integration Won't Load
Check logs: `Settings → System → Logs → "z2m_irrigation"`

### Valves Not Discovered
1. Verify MQTT base topic
2. Check Zigbee2MQTT pairing
3. Use "Manual Topics" if needed

### Sensors Showing 0 After Restart
1. Check `/config/z2m_irrigation.db` exists
2. Check logs for "Database initialized"
3. Restart integration

See `TROUBLESHOOTING.md` for complete guide.

---

## 📊 Sensor Reference

### Per Valve (17 Total)
- **Real-time:** flow, session used, duration, remaining
- **Resettable:** total liters, minutes, count
- **Lifetime:** total liters, minutes, count (never reset)
- **Time-based (NEW):** last 24h, last 7d (liters & minutes)
- **Device:** battery, link quality

---

## ⚙️ Services

### `start_liters`
Water by volume target (auto-stops at target)

### `start_timed`
Water for duration (stops after time elapsed)

### `reset_totals`
Reset resettable totals (lifetime preserved)

### `rescan`
Re-discover valves from MQTT

---

## 🤝 Contributing

Issues and PRs welcome!

**GitHub:** https://github.com/Zebra-zzz/z2m-irrigation

---

## 📝 License

MIT License

---

**Happy Watering!** 💧🌱

For complete documentation, see the included `.md` files.
