# ⏰ Scheduler Status - v3.0.0

## Current Status: Temporarily Disabled

The smart scheduler feature is **temporarily disabled** in v3.0.0 while we migrate it from Supabase to local SQLite.

---

## What Still Works ✅

### Core Irrigation (100% Functional)
- ✅ Manual watering via services
- ✅ All sensors and tracking
- ✅ Lifetime and resettable totals
- ✅ Time-based tracking (24h, 7d)
- ✅ Session history
- ✅ Complete local persistence

### Services Available
```yaml
# Start by liters
service: z2m_irrigation.start_liters
data:
  valve: "Water Valve 1"
  liters: 50

# Start by time
service: z2m_irrigation.start_timed
data:
  valve: "Water Valve 1"
  minutes: 10

# Reset totals
service: z2m_irrigation.reset_totals
data:
  valve: "Water Valve 1"  # Optional - omit to reset all
```

---

## What's Temporarily Disabled ⏸️

### Scheduler Services (v3.0.0)
- ❌ `z2m_irrigation.create_schedule`
- ❌ `z2m_irrigation.update_schedule`
- ❌ `z2m_irrigation.delete_schedule`
- ❌ `z2m_irrigation.enable_schedule`
- ❌ `z2m_irrigation.disable_schedule`
- ❌ `z2m_irrigation.run_schedule`
- ❌ `z2m_irrigation.reload_schedules`

**Why?** These require Supabase tables which are being migrated to local SQLite.

---

## Workaround: Use Home Assistant Automations

### Time-Based Schedule
```yaml
automation:
  - alias: "Water Front Garden Daily"
    trigger:
      - platform: time
        at: "06:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.gw2000c_rain_rate
        below: 0.1
    action:
      - service: z2m_irrigation.start_liters
        data:
          valve: "Front Garden"
          liters: 50
```

### Interval-Based Schedule
```yaml
automation:
  - alias: "Water Every 8 Hours"
    trigger:
      - platform: time_pattern
        hours: "/8"  # Every 8 hours
    action:
      - service: z2m_irrigation.start_liters
        data:
          valve: "Back Garden"
          liters: 30
```

### Weather-Aware Schedule
```yaml
automation:
  - alias: "Smart Watering - Weather Aware"
    trigger:
      - platform: time
        at: "06:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.gw2000c_daily_rain
        below: 5  # No watering if > 5mm rain today
      - condition: numeric_state
        entity_id: sensor.gw2000c_wind_speed
        below: 25
      - condition: numeric_state
        entity_id: sensor.soil_moisture
        below: 50  # Only water if dry
    action:
      - service: z2m_irrigation.start_liters
        data:
          valve: "Front Garden"
          liters: "{{ states('input_number.front_garden_liters')|float }}"
```

### Multiple Zones (Parallel)
```yaml
automation:
  - alias: "Water All Zones"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      # All zones start simultaneously
      - service: z2m_irrigation.start_liters
        data:
          valve: "Front Garden"
          liters: 50
      - service: z2m_irrigation.start_liters
        data:
          valve: "Back Garden"
          liters: 30
      - service: z2m_irrigation.start_liters
        data:
          valve: "Lilly Pilly"
          liters: 80
```

### Multiple Zones (Sequential)
```yaml
automation:
  - alias: "Water All Zones Sequential"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      # Front garden
      - service: z2m_irrigation.start_liters
        data:
          valve: "Front Garden"
          liters: 50
      # Wait for it to finish (estimate based on flow rate)
      - delay:
          minutes: 15
      # Back garden
      - service: z2m_irrigation.start_liters
        data:
          valve: "Back Garden"
          liters: 30
      - delay:
          minutes: 10
      # Hedge
      - service: z2m_irrigation.start_liters
        data:
          valve: "Lilly Pilly"
          liters: 80
```

---

## Coming in v3.1.0 🚀

### Scheduler Features (Planned)
- ✅ Local SQLite schedule storage
- ✅ Time-based schedules
- ✅ Interval-based schedules
- ✅ Weather-aware conditions
- ✅ Schedule management UI
- ✅ Run history tracking

**ETA:** Next major release

---

## FAQ

### Q: Why was the scheduler disabled?
**A:** The scheduler relied on Supabase cloud database. To make everything 100% local, we need to migrate scheduler storage to SQLite. This requires careful design to maintain all features.

### Q: Will my v2.x schedules work?
**A:** No, schedules from v2.x (which used Supabase) won't carry over. You'll need to recreate them as automations or wait for v3.1.0.

### Q: Should I downgrade to v2.x?
**A:** Only if you absolutely need the scheduler feature right now. Otherwise, automations work great and you get the benefit of 100% local persistence for all your irrigation data.

### Q: Can I use both v2.x and v3.0.0?
**A:** No, you need to choose one or the other. We recommend v3.0.0 for its local persistence and time-based tracking.

### Q: How do I track what I watered?
**A:** All tracking still works! Use the new time-based sensors:
- `sensor.xxx_last_24h` - What you watered today
- `sensor.xxx_last_7_days` - Weekly total
- `sensor.xxx_lifetime_total` - All-time total

---

## Current Automation You Shared

Your automation still works perfectly! Just calls the service:

```yaml
alias: Irrigation — Smart Daily (Liters, Parallel)
# ... your triggers and conditions ...
actions:
  - service: z2m_irrigation.start_liters
    data:
      valve: Front Garden
      liters: "{{ front_liters|int }}"
  - service: z2m_irrigation.start_liters
    data:
      valve: Back Garden
      liters: "{{ back_liters|int }}"
  - service: z2m_irrigation.start_liters
    data:
      valve: Lilly Pilly
      liters: "{{ hedge_liters|int }}"
```

**This works in v3.0.0!** ✅

---

## Summary

- ✅ **Core irrigation:** Fully functional and 100% local
- ✅ **Your automation:** Works perfectly
- ✅ **Time-based tracking:** New feature, works great
- ⏸️ **Built-in scheduler:** Temporarily disabled
- 🚀 **Alternative:** Use HA automations (same functionality)
- 🔜 **Future:** Scheduler coming back in v3.1.0 with local storage

**Recommendation:** Upgrade to v3.0.0 and use automations for scheduling. You get better local persistence and the new time-based sensors!
