# ⚡ Quick Start Guide - Z2M Irrigation v2.0

Get up and running in 15 minutes!

## 🚀 Installation (5 minutes)

1. **Install via HACS:**
   - HACS → Integrations → Search "Z2M Irrigation"
   - Click Install → Restart Home Assistant

2. **Add Integration:**
   - Settings → Devices & Services → Add Integration
   - Search "Z2M Irrigation"
   - Configure MQTT base topic (default: `zigbee2mqtt`)
   - Done! Valves auto-discovered

3. **Verify:**
   - Check Devices & Services → Z2M Irrigation
   - Should see all your Sonoff SWV valves
   - Each valve has 12+ entities

## 🎮 Basic Usage (5 minutes)

### Manual Control

**Start valve for 10 minutes:**
```yaml
Developer Tools → Services
Service: z2m_irrigation.start_timed
valve: Water Valve 1
minutes: 10
```

**Start valve for 50 liters:**
```yaml
Service: z2m_irrigation.start_liters
valve: Water Valve 1
liters: 50
```

**Stop immediately:**
```yaml
Service: switch.turn_off
entity_id: switch.water_valve_1_valve
```

### Dashboard Control

1. Go to Overview dashboard
2. Find your valve switch: `switch.water_valve_1_valve`
3. Toggle on/off
4. Check sensors:
   - Flow rate: `sensor.water_valve_1_flow`
   - Session used: `sensor.water_valve_1_session_used`
   - Remaining time: `sensor.water_valve_1_remaining_time`

## 📅 Create Schedule (5 minutes)

### Simple Morning Watering

```yaml
Developer Tools → Services
Service: z2m_irrigation.create_schedule

data:
  name: "Morning Lawn"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00"]
  run_type: "duration"
  run_value: 15
```

**Done!** Will run at 6 AM daily for 15 minutes.

### Weekday Schedule

```yaml
Service: z2m_irrigation.create_schedule

data:
  name: "Weekday Garden"
  valve: "Water Valve 2"
  schedule_type: "time_based"
  times: ["07:00", "19:00"]
  days_of_week: [0, 1, 2, 3, 4]  # Mon-Fri
  run_type: "volume"
  run_value: 30
```

**Done!** Runs Mon-Fri at 7 AM and 7 PM for 30 liters.

### Interval Schedule

```yaml
Service: z2m_irrigation.create_schedule

data:
  name: "Potted Plants"
  valve: "Water Valve 3"
  schedule_type: "interval"
  interval_hours: 12
  run_type: "duration"
  run_value: 5
```

**Done!** Runs every 12 hours for 5 minutes.

## 🎨 Install Dashboard (Optional)

1. **Add helpers:**
   - Copy `dashboard-helpers.yaml` to `configuration.yaml`
   - Restart Home Assistant

2. **Create dashboard:**
   - Settings → Dashboards → Add Dashboard
   - Name: "Irrigation Controller"
   - Edit → Raw Config Editor
   - Paste `dashboard-irrigation-controller.yaml`
   - Save

3. **Update entity names:**
   - Replace `water_valve_1` with your valve names
   - Update valve friendly names

**See `DASHBOARD-SETUP.md` for detailed instructions**

## 🔧 Common Tasks

### Get Schedule ID

**Option 1: Supabase**
1. Open Supabase dashboard
2. Table Editor → `irrigation_schedules`
3. Find schedule by name
4. Copy `id` value

**Option 2: Logs**
1. Create schedule
2. Check Home Assistant logs
3. Look for: `Added schedule 'Name' (ID: abc123...)`

### Disable Schedule

```yaml
Service: z2m_irrigation.disable_schedule
data:
  schedule_id: "YOUR-ID-HERE"
```

### Run Schedule Now

```yaml
Service: z2m_irrigation.run_schedule_now
data:
  schedule_id: "YOUR-ID-HERE"
```

### Delete Schedule

```yaml
Service: z2m_irrigation.delete_schedule
data:
  schedule_id: "YOUR-ID-HERE"
```

## 🌦️ Add Smart Conditions

Make schedules weather-aware:

```yaml
Service: z2m_irrigation.create_schedule

data:
  name: "Smart Lawn"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00"]
  run_type: "duration"
  run_value: 15
  conditions:
    soil_moisture_entity: "sensor.lawn_moisture"
    max_moisture: 50
    skip_if_rain: true
```

**Conditions:**
- `soil_moisture_entity` - Sensor entity ID
- `max_moisture` - Skip if above this %
- `min_temp` - Skip if below this °C
- `max_temp` - Skip if above this °C
- `skip_if_rain` - Skip if rained recently

## 📊 View History

### Session History (Supabase)
```
Table: irrigation_sessions
Shows: All watering sessions
Columns: start_time, end_time, duration, volume, valve
```

### Schedule Runs (Supabase)
```
Table: schedule_runs
Shows: All schedule executions
Columns: started_at, status, skip_reason, actual_volume
```

### Home Assistant
```
Developer Tools → Statistics
Select: sensor.water_valve_1_total
Period: Month
```

## 🎯 Next Steps

1. ✅ **Test a schedule**
   - Create simple morning schedule
   - Use `run_schedule_now` to test
   - Check Supabase for run record

2. ✅ **Monitor first auto-run**
   - Wait for scheduled time
   - Watch valve turn on
   - Verify duration/volume correct
   - Check logs for any issues

3. ✅ **Add more schedules**
   - Cover all your valves
   - Set different times per zone
   - Adjust based on plant needs

4. ✅ **Add conditions**
   - Install weather integration
   - Add soil moisture sensors
   - Enable smart skipping

5. ✅ **Install dashboard**
   - Full visual control
   - Easy schedule creation
   - Beautiful monitoring

## 🆘 Troubleshooting

### Valves Not Found
```yaml
Service: z2m_irrigation.rescan
```
Wait 30 seconds, check again.

### Schedule Not Running
1. Check `enabled = true` in Supabase
2. Verify `next_run_at` is in future
3. Check logs for skip reasons

### Valve Won't Stop
```yaml
# Emergency stop
Service: switch.turn_off
target:
  entity_id: switch.water_valve_1_valve
```

### Reset Everything
```yaml
Service: z2m_irrigation.reset_totals
# Resets all counters to 0
```

## 📚 Full Documentation

- **Scheduling Guide:** `SCHEDULING.md` - Complete scheduling reference
- **Dashboard Setup:** `DASHBOARD-SETUP.md` - Dashboard installation
- **Installation:** `INSTALLATION.md` - Detailed setup guide
- **README:** `README.md` - Feature overview
- **Changelog:** `CHANGELOG.md` - Version history

## 🎉 You're Ready!

Your irrigation system is now:
- ✅ Automated with schedules
- ✅ Weather-aware (if configured)
- ✅ Monitored in real-time
- ✅ Logged to database
- ✅ Triple-failsafe protected

**Enjoy your smart irrigation system!** 💧

---

**Need Help?**
- Issues: https://github.com/Zebra-zzz/z2m-irrigation/issues
- Discussions: https://github.com/Zebra-zzz/z2m-irrigation/discussions
