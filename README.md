# Z2M Irrigation (Sonoff Valves)

A Home Assistant custom integration for controlling and logging Sonoff Zigbee water valves via Zigbee2MQTT, with comprehensive session history tracking visible directly in the HA UI.

## Features

- **100% UI Configuration** - No YAML required
- **Multi-Valve Support** - Add/edit/remove valves through options flow
- **Flow Monitoring** - Real-time flow rate with configurable noise floor
- **Precise Volume Tracking** - Accurate litre integration with persistent totals
- **Smart Control Modes**:
  - **Timed** - Auto-off after X minutes
  - **Volume** - Auto-off after X litres dispensed
  - **Manual** - Direct on/off control
- **Session History** - Dedicated sidebar panel for viewing all irrigation sessions
- **Logbook Integration** - Friendly session start/end entries
- **Failsafe Protection** - Automatic retry if valve doesn't respond
- **Services for Automation** - Easy integration with HA automations

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu → "Custom repositories"
4. Add this repository URL: `https://github.com/your-username/ha-z2m-irrigation`
5. Category: Integration
6. Click "Add"
7. Find "Z2M Irrigation (Sonoff Valves)" and click "Download"
8. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Extract to `custom_components/z2m_irrigation/` in your config directory
3. Restart Home Assistant

## Setup

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Z2M Irrigation (Sonoff Valves)"
4. Enter your first valve configuration:
   - **Valve Name**: e.g., "Water Valve 1"
   - **Zigbee2MQTT Topic**: e.g., `zigbee2mqtt/Water Valve 1`
   - **Flow Unit**: `lpm` (L/min) or `m3h` (m³/h)
   - **Max Runtime**: Default failsafe timeout (minutes)
   - **Noise Floor**: Ignore flow below this threshold (L/min)

### Adding More Valves

1. Go to the integration in **Settings** → **Devices & Services**
2. Click **Configure**
3. Select "Add New Valve"

## MQTT Configuration

Ensure your Zigbee2MQTT is publishing valve data. The integration expects messages like:

```json
{
  "state": "ON",
  "flow": 0.42,
  "battery": 96,
  "linkquality": 180,
  "last_seen": "2025-10-14T22:25:33",
  "current_device_status": "online"
}
```

**Topics**:
- Subscribe: `zigbee2mqtt/Water Valve 1`
- Publish: `zigbee2mqtt/Water Valve 1/set` with payload `{"state":"ON"}` or `{"state":"OFF"}`

## Entities Created

For each valve:

- **Switch**: `switch.water_valve_1` - Turn valve on/off
- **Sensor**: `sensor.water_valve_1_flow` - Current flow rate (L/min)
- **Sensor**: `sensor.water_valve_1_total` - Cumulative litres (persisted)
- **Sensor**: `sensor.water_valve_1_session_used` - Litres in current session
- **Sensor**: `sensor.water_valve_1_battery` - Battery percentage
- **Sensor**: `sensor.water_valve_1_link_quality` - Zigbee link quality

## Services

### `z2m_irrigation.start_timed`

Start valve with timed auto-off.

```yaml
service: z2m_irrigation.start_timed
data:
  name: "Water Valve 1"
  minutes: 30
```

### `z2m_irrigation.start_litres`

Start valve until target litres reached.

```yaml
service: z2m_irrigation.start_litres
data:
  name: "Water Valve 1"
  litres: 50
  hard_timeout_min: 120  # optional failsafe
```

### `z2m_irrigation.stop`

Manually stop a valve.

```yaml
service: z2m_irrigation.stop
data:
  name: "Water Valve 1"
```

### `z2m_irrigation.reset_total`

Reset the total litres counter.

```yaml
service: z2m_irrigation.reset_total
data:
  name: "Water Valve 1"
```

## Session History Panel

Access via the sidebar: **Irrigation Sessions**

Features:
- Filter by valve, date range
- Sortable columns (click headers)
- View session details: start/end time, duration, litres, mode, how it ended
- Delete individual sessions
- Clear all sessions
- Export to CSV

## Automation Examples

### Water Garden Every Morning

```yaml
automation:
  - alias: "Morning Garden Watering"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: z2m_irrigation.start_timed
        data:
          name: "Garden Valve"
          minutes: 20
```

### Fill 50L Tank

```yaml
automation:
  - alias: "Fill Water Tank"
    trigger:
      - platform: numeric_state
        entity_id: sensor.tank_level
        below: 20
    action:
      - service: z2m_irrigation.start_litres
        data:
          name: "Tank Fill Valve"
          litres: 50
```

### Emergency Shutoff on High Flow

```yaml
automation:
  - alias: "Emergency Shutoff"
    trigger:
      - platform: numeric_state
        entity_id: sensor.water_valve_1_flow
        above: 10
        for:
          seconds: 5
    action:
      - service: z2m_irrigation.stop
        data:
          name: "Water Valve 1"
      - service: notify.mobile_app
        data:
          message: "Emergency shutoff triggered - abnormal flow detected!"
```

## Troubleshooting

### Totals Reset After Restart

The integration persists totals to `.storage/z2m_irrigation_totals`. If this file is corrupted or deleted, totals will reset. Backups are recommended.

### Noisy Flow Readings

Adjust the **Noise Floor** in valve options. Any flow below this threshold (L/min) will be ignored. Default is 0.3 L/min.

### Valve Doesn't Turn Off

The integration includes a failsafe:
1. Publishes OFF command
2. Waits 5 seconds
3. Checks if valve is still ON
4. If yes, publishes OFF again

Check your Zigbee2MQTT logs for connection issues.

### Sessions Not Appearing

1. Check that the integration is loaded: **Settings** → **System** → **Logs**
2. Verify WebSocket API is working: Browser console → Network tab
3. Clear browser cache and reload

## Development

### File Structure

```
custom_components/z2m_irrigation/
├── __init__.py          # Main integration logic
├── config_flow.py       # UI configuration flows
├── const.py             # Constants
├── sensor.py            # Sensor entities
├── switch.py            # Switch entities
├── websocket.py         # WebSocket API handlers
├── logbook.py           # Logbook integration
├── manifest.json        # Integration metadata
├── services.yaml        # Service definitions
├── strings.json         # UI strings
├── translations/
│   └── en.json          # English translations
└── panel/
    └── panel.js         # Frontend session viewer
```

## Credits

Built with ❤️ for the Home Assistant community.

## License

MIT License - see [LICENSE](LICENSE)
