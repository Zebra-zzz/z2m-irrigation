# 🗓️ Irrigation Scheduling Guide

Comprehensive guide for using the smart irrigation scheduling system in Z2M Irrigation v2.0+.

## Quick Start

### Create a Simple Time-Based Schedule

Water your lawn every morning at 6:00 AM for 15 minutes:

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Morning Lawn Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00"]
  run_type: "duration"
  run_value: 15
  enabled: true
```

### Create an Interval-Based Schedule

Water potted plants every 12 hours for 2 liters:

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Potted Plants"
  valve: "Water Valve 2"
  schedule_type: "interval"
  interval_hours: 12
  run_type: "volume"
  run_value: 2
  enabled: true
```

## Schedule Types

### 1. Time-Based Schedules

Run at specific times on specific days.

**Daily Schedule (Every Day)**
```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Daily Garden Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00", "18:00"]  # 6 AM and 6 PM
  days_of_week: null  # null = every day
  run_type: "duration"
  run_value: 20
```

**Weekday Schedule**
```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Weekday Lawn"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["07:00"]
  days_of_week: [0, 1, 2, 3, 4]  # Monday-Friday (0=Mon, 6=Sun)
  run_type: "duration"
  run_value: 15
```

**Weekend Schedule**
```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Weekend Deep Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["08:00"]
  days_of_week: [5, 6]  # Saturday and Sunday
  run_type: "volume"
  run_value: 50
```

### 2. Interval-Based Schedules

Run automatically after a certain amount of time has passed since the last run.

**Every 6 Hours**
```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Greenhouse Misting"
  valve: "Water Valve 3"
  schedule_type: "interval"
  interval_hours: 6
  run_type: "duration"
  run_value: 5
```

**Every 24 Hours** (Alternative to time-based)
```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Daily Drip"
  valve: "Water Valve 2"
  schedule_type: "interval"
  interval_hours: 24
  run_type: "volume"
  run_value: 10
```

## Smart Conditions (Weather-Aware)

Make your schedules smarter by adding conditions that check weather and sensors.

### Skip if Soil Moisture is High

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Smart Lawn Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00"]
  run_type: "duration"
  run_value: 15
  conditions:
    soil_moisture_entity: "sensor.lawn_moisture"
    max_moisture: 50  # Skip if moisture >= 50%
```

### Skip Based on Temperature

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Temperature-Aware Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00", "18:00"]
  run_type: "duration"
  run_value: 20
  conditions:
    min_temp: 15  # Only run if temp >= 15°C
    max_temp: 35  # Skip if temp >= 35°C
```

### Skip if Rained Recently

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Rain-Aware Watering"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00"]
  run_type: "duration"
  run_value: 15
  conditions:
    skip_if_rain: true
```

### Combined Conditions

```yaml
service: z2m_irrigation.create_schedule
data:
  name: "Fully Smart Schedule"
  valve: "Water Valve 1"
  schedule_type: "time_based"
  times: ["06:00", "18:00"]
  days_of_week: [0, 1, 2, 3, 4, 5, 6]
  run_type: "volume"
  run_value: 30
  conditions:
    soil_moisture_entity: "sensor.lawn_moisture"
    max_moisture: 40
    min_temp: 10
    max_temp: 38
    skip_if_rain: true
```

## Managing Schedules

### Update a Schedule

```yaml
service: z2m_irrigation.update_schedule
data:
  schedule_id: "abc123-schedule-id"
  times: ["07:00", "19:00"]  # Change watering times
  run_value: 25  # Increase duration
```

### Enable/Disable Schedules

**Disable for Winter**
```yaml
service: z2m_irrigation.disable_schedule
data:
  schedule_id: "abc123-schedule-id"
```

**Re-enable for Spring**
```yaml
service: z2m_irrigation.enable_schedule
data:
  schedule_id: "abc123-schedule-id"
```

### Run Schedule Immediately

Test or manually trigger a schedule:

```yaml
service: z2m_irrigation.run_schedule_now
data:
  schedule_id: "abc123-schedule-id"
```

### Delete a Schedule

```yaml
service: z2m_irrigation.delete_schedule
data:
  schedule_id: "abc123-schedule-id"
```

## Automation Examples

### Seasonal Adjustments

Automatically adjust watering duration based on season:

```yaml
automation:
  - alias: "Summer Watering"
    trigger:
      - platform: state
        entity_id: sensor.season
        to: "summer"
    action:
      - service: z2m_irrigation.update_schedule
        data:
          schedule_id: "your-schedule-id"
          run_value: 30  # 30 minutes in summer

  - alias: "Spring/Fall Watering"
    trigger:
      - platform: state
        entity_id: sensor.season
        to: ["spring", "fall"]
    action:
      - service: z2m_irrigation.update_schedule
        data:
          schedule_id: "your-schedule-id"
          run_value: 20  # 20 minutes in spring/fall

  - alias: "Winter - Disable"
    trigger:
      - platform: state
        entity_id: sensor.season
        to: "winter"
    action:
      - service: z2m_irrigation.disable_schedule
        data:
          schedule_id: "your-schedule-id"
```

### Manual Skip Next Run

Create a button to skip the next scheduled run:

```yaml
script:
  skip_morning_watering:
    alias: "Skip Morning Watering"
    sequence:
      - service: z2m_irrigation.disable_schedule
        data:
          schedule_id: "morning-schedule-id"
      - delay:
          hours: 2
      - service: z2m_irrigation.enable_schedule
        data:
          schedule_id: "morning-schedule-id"
```

### Vacation Mode

Disable all irrigation schedules when away:

```yaml
automation:
  - alias: "Vacation Mode - Disable Irrigation"
    trigger:
      - platform: state
        entity_id: input_boolean.vacation_mode
        to: "on"
    action:
      - service: z2m_irrigation.disable_schedule
        data:
          schedule_id: "schedule-1"
      - service: z2m_irrigation.disable_schedule
        data:
          schedule_id: "schedule-2"
      # ... repeat for each schedule

  - alias: "Return Home - Enable Irrigation"
    trigger:
      - platform: state
        entity_id: input_boolean.vacation_mode
        to: "off"
    action:
      - service: z2m_irrigation.enable_schedule
        data:
          schedule_id: "schedule-1"
      - service: z2m_irrigation.enable_schedule
        data:
          schedule_id: "schedule-2"
```

## Schedule Data Structure

### Schedule Object

```json
{
  "id": "uuid-here",
  "name": "Morning Lawn Watering",
  "valve_topic": "Water Valve 1",
  "enabled": true,
  "schedule_type": "time_based",
  "times": ["06:00", "18:00"],
  "days_of_week": [0, 1, 2, 3, 4, 5, 6],
  "interval_hours": null,
  "run_type": "duration",
  "run_value": 15.0,
  "conditions": {
    "soil_moisture_entity": "sensor.lawn_moisture",
    "max_moisture": 50
  },
  "priority": 0,
  "created_at": "2025-10-20T00:00:00Z",
  "updated_at": "2025-10-20T00:00:00Z",
  "last_run_at": "2025-10-20T06:00:00Z",
  "next_run_at": "2025-10-21T06:00:00Z"
}
```

### Schedule Run Object

```json
{
  "id": "run-uuid",
  "schedule_id": "schedule-uuid",
  "session_id": "session-uuid",
  "started_at": "2025-10-20T06:00:00Z",
  "completed_at": "2025-10-20T06:15:00Z",
  "status": "completed",
  "skip_reason": null,
  "actual_duration": 15.2,
  "actual_volume": 45.5
}
```

**Status Values:**
- `running` - Currently executing
- `completed` - Finished successfully
- `skipped` - Skipped due to conditions
- `failed` - Error occurred
- `cancelled` - Manually stopped

**Skip Reasons:**
- `Soil moisture X% >= Y%` - Moisture too high
- `Temperature X°C outside range` - Too hot/cold
- `Rain detected` - Rained recently
- `Manual` - User intervention

## WebSocket API

For custom dashboards and cards:

### List All Schedules

```javascript
hass.callWS({
  type: "z2m_irrigation/schedules/list"
}).then(result => {
  console.log(result.schedules);
});
```

### Get Schedule Details

```javascript
hass.callWS({
  type: "z2m_irrigation/schedules/get",
  schedule_id: "your-schedule-id"
}).then(result => {
  console.log(result.schedule);
});
```

### Get Schedule Run History

```javascript
hass.callWS({
  type: "z2m_irrigation/schedules/runs",
  schedule_id: "your-schedule-id",
  limit: 50
}).then(result => {
  console.log(result.runs);
});
```

## Best Practices

### 1. Start Simple
Begin with basic time-based schedules. Add conditions once you have sensors.

### 2. Use Meaningful Names
Good: "Front Lawn Morning", "Garden Beds Evening"
Bad: "Schedule 1", "Test Schedule"

### 3. Test New Schedules
Use `run_schedule_now` to test before waiting for the scheduled time.

### 4. Monitor Run History
Check the `schedule_runs` table in Supabase to see:
- When schedules ran
- Why they were skipped
- Actual water usage

### 5. Adjust Seasonally
Use automations to update `run_value` based on temperature or season.

### 6. Set Priorities (Future Feature)
If schedules overlap, higher priority runs first (currently all priority 0).

## Troubleshooting

### Schedule Not Running

1. **Check if enabled**: `schedule.enabled = true`
2. **Check next_run_at**: Is it in the future?
3. **Check conditions**: View logs for skip reasons
4. **Check valve exists**: Valve topic must match exactly

### Schedule Running Too Often/Rarely

**Time-Based:**
- Verify times are in HH:MM format: `"06:00"`, `"18:30"`
- Check timezone in Home Assistant matches your location
- Verify days_of_week: `[0=Mon, 1=Tue, ..., 6=Sun]`

**Interval-Based:**
- Check `last_run_at` - intervals calculated from last run
- If never run, starts immediately then waits interval

### Conditions Not Working

- **Soil Moisture**: Ensure sensor entity_id is correct and reporting numeric values
- **Temperature**: Weather integration must be configured
- **Rain**: Weather integration must report precipitation data

## Future Enhancements

Planned features:
- [ ] Priority-based execution (queue multiple valves)
- [ ] Zone grouping (run valves in sequence)
- [ ] Calendar view in frontend
- [ ] Custom entities per schedule (switches, sensors)
- [ ] Template-based conditions (full HA templates)
- [ ] Notification on skip/completion
- [ ] Historical statistics (water saved by skips)

---

## Need Help?

- **Issues**: https://github.com/Zebra-zzz/z2m-irrigation/issues
- **Discussions**: https://github.com/Zebra-zzz/z2m-irrigation/discussions
- **Documentation**: https://github.com/Zebra-zzz/z2m-irrigation
