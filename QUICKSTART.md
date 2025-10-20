# Quick Start Guide

## 5-Minute Setup

### 1. Prerequisites Check

✅ Home Assistant running
✅ MQTT configured
✅ Zigbee2MQTT with Sonoff valves paired
✅ Know your valve's Z2M friendly name (e.g., "Water Valve 1")

### 2. Install Integration

**Copy files to:**
```
/config/custom_components/z2m_irrigation/
```

**Restart Home Assistant**

### 3. Add Integration

1. Settings → Devices & Services
2. Add Integration → "Z2M Irrigation (Sonoff Valves)"
3. Fill in:
   - **Valve Name**: Water Valve 1
   - **Topic**: zigbee2mqtt/Water Valve 1
   - **Flow Unit**: lpm
   - **Max Runtime**: 120
   - **Noise Floor**: 0.3

### 4. Test It

**Turn on valve:**
```yaml
service: switch.turn_on
target:
  entity_id: switch.water_valve_1
```

**Watch flow sensor update:**
- `sensor.water_valve_1_flow` should show current L/min

**Run timed session:**
```yaml
service: z2m_irrigation.start_timed
data:
  name: "Water Valve 1"
  minutes: 2
```

**View session history:**
- Sidebar → "Irrigation Sessions"

## Common Use Cases

### Morning Garden Watering

```yaml
automation:
  - alias: "Water Garden"
    trigger:
      platform: time
      at: "06:00:00"
    action:
      service: z2m_irrigation.start_timed
      data:
        name: "Garden Valve"
        minutes: 15
```

### Fill Water Tank to 100L

```yaml
automation:
  - alias: "Fill Tank"
    trigger:
      platform: state
      entity_id: input_boolean.fill_tank
      to: "on"
    action:
      - service: z2m_irrigation.start_litres
        data:
          name: "Tank Valve"
          litres: 100
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.fill_tank
```

### Emergency Shutoff Button

```yaml
automation:
  - alias: "Emergency Stop All Valves"
    trigger:
      platform: state
      entity_id: input_button.emergency_stop
      to: "on"
    action:
      - service: z2m_irrigation.stop
        data:
          name: "Garden Valve"
      - service: z2m_irrigation.stop
        data:
          name: "Tank Valve"
      - service: notify.mobile_app
        data:
          message: "All irrigation valves stopped"
```

## Dashboard Card Example

```yaml
type: entities
title: Garden Irrigation
entities:
  - entity: switch.garden_valve
    name: Valve Control
  - entity: sensor.garden_valve_flow
    name: Current Flow
  - entity: sensor.garden_valve_session_used
    name: Session Total
  - entity: sensor.garden_valve_total
    name: All-Time Total
  - entity: sensor.garden_valve_battery
    name: Battery
```

## Tuning Tips

### Noise Floor

If your flow sensor shows small readings when valve is off:
- Increase noise floor (e.g., 0.5 L/min)
- Edit via Configuration → Integrations → Z2M Irrigation → Configure

### Max Runtime Failsafe

For critical applications, reduce max runtime:
- 30 min for indoor uses
- 60 min for gardens
- 120 min for large area watering

### Flow Unit Selection

- **lpm**: Most Sonoff valves report in L/min directly
- **m3h**: If Z2M shows m³/h, integration converts automatically

## Next Steps

- ✅ Add more valves via Configure → Add New Valve
- ✅ Explore session history in sidebar panel
- ✅ Create automations for scheduled watering
- ✅ Set up notifications for low battery
- ✅ Export session data to CSV for analysis

## Support

Check logs if issues occur:
- Settings → System → Logs
- Filter: "z2m_irrigation"

Common issues:
- **No entities**: Check MQTT topic matches Z2M exactly
- **Flow always 0**: Check flow unit setting
- **Valve won't turn off**: Check Z2M connection quality

Enjoy automated irrigation! 💧🌱
