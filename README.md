# 💧 Z2M Irrigation (Sonoff Valves)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/Zebra-zzz/z2m-irrigation)

Advanced Home Assistant custom integration for **Sonoff SWV** smart water valves via **Zigbee2MQTT**.

## ✨ Features

- 🔄 **Automatic Discovery** - Finds all Sonoff SWV valves via Zigbee2MQTT
- ⏱️ **Timed Irrigation** - Set valves to run for specific minutes (native Zigbee control)
- 💧 **Volume-Based Irrigation** - Run valves for specific liters (native Zigbee control)
- 📊 **Real-time Monitoring** - Flow rate, session usage, and totals
- 📈 **Session History** - Automatic logging to Home Assistant's local database
- 🔋 **Battery & Signal Monitoring** - Track device health
- ⚡ **Local Control** - Commands sent directly to Zigbee device for offline operation

## 📦 Installation

### Via HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Z2M Irrigation" in HACS
3. Click Install
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/z2m_irrigation` folder to your Home Assistant config directory
2. Restart Home Assistant
3. Go to **Settings** → **Devices & Services** → **Add Integration**
4. Search for "Z2M Irrigation (Sonoff Valves)"

## 🎛️ Entities per Valve

### Controls
- 🚰 **Valve** (switch) - Manual on/off control
- ⏱️ **Run for Minutes** (number) - Set duration and start valve
- 💧 **Run for Liters** (number) - Set volume and start valve

### Sensors
- 🌊 **Flow** (L/min) - Current flow rate
- 💧 **Session Used** (L) - Water used in current session
- ⏱️ **Session Duration** (min) - How long current session has been running
- ⏳ **Remaining Time** (min) - Time left for timed runs (with estimates)
- 💧 **Remaining Liters** (L) - Liters left for volume runs (with estimates)
- 📊 **Total** (L) - Total water used all-time
- ⏲️ **Total Minutes** (min) - Total runtime all-time
- 🔢 **Session Count** - Number of sessions
- 🔋 **Battery** (%) - Battery level
- 📡 **Link Quality** - Zigbee signal strength

## 🛠️ Services

### `z2m_irrigation.start_timed`
Start valve for specified minutes using native Zigbee timer.
```yaml
service: z2m_irrigation.start_timed
data:
  valve: "Water Valve 1"
  minutes: 15
```

### `z2m_irrigation.start_liters`
Start valve for specified liters using native Zigbee volume control.
```yaml
service: z2m_irrigation.start_liters
data:
  valve: "Water Valve 1"
  liters: 50
```

### `z2m_irrigation.reset_totals`
Reset total counters and session count.
```yaml
service: z2m_irrigation.reset_totals
data:
  valve: "Water Valve 1"  # Optional - omit to reset all valves
```

### `z2m_irrigation.rescan`
Re-request device list from Zigbee2MQTT.
```yaml
service: z2m_irrigation.rescan
```

## ⚙️ Configuration Options

Access via the gear icon in the integration:

- **MQTT Base Topic** - Default: `zigbee2mqtt`
- **Manual Valves** - One friendly name per line (fallback if discovery fails)
- **Flow Scale** - Multiplier for flow rate conversion (default: `16.667`)
  - Sonoff SWV reports flow in m³/h, which is automatically converted to L/min
  - Adjust only if your device uses different units

## 📊 Session History

All irrigation sessions are automatically logged to Home Assistant's local database (recorder):
- Session start/end times
- Duration and volume used
- Average flow rate
- Trigger type (manual/timed/volume)

View history in the **Energy** dashboard or create custom statistics cards.

## 🔧 How It Works

### Discovery
The integration subscribes to Zigbee2MQTT bridge topics:
- `${base}/bridge/devices`
- `${base}/bridge/config/devices`

It identifies Sonoff SWV devices and subscribes to each valve's topic.

### Triple Failsafe System

**Volume-Based Irrigation (3 layers):**
1. 🔵 **Native Device Control** - Device programmed to stop at target liters
2. 🟡 **Real-Time Monitoring** - HA checks flow every 2-4 seconds
3. 🔴 **Forced Shutoff** - HA sends OFF if target exceeded

**Time-Based Irrigation (3 layers):**
1. 🔵 **Native Device Control** - Device programmed to stop at target time
2. 🟡 **Real-Time Monitoring** - HA checks elapsed time every update
3. 🔴 **Backup Timer** - HA timer forces OFF at exact target time

**Safety Guarantee**: Even if the Zigbee device completely fails or disconnects, Home Assistant will ALWAYS force the valve OFF when targets are reached. All failsafe activations are logged as WARNINGS for visibility.

### Data Storage
- **Real-time data**: Tracked in memory for instant updates
- **Historical data**: Stored in Home Assistant's local SQLite/PostgreSQL database
- **No cloud required**: Everything runs on your local server

## 🎨 Customization

### Dashboard Example
```yaml
type: entities
title: Garden Irrigation
entities:
  - entity: switch.water_valve_1_valve
  - entity: sensor.water_valve_1_flow
  - entity: sensor.water_valve_1_session_used
  - entity: sensor.water_valve_1_session_duration
  - entity: number.water_valve_1_run_for_minutes
  - entity: number.water_valve_1_run_for_liters
```

## 🐛 Troubleshooting

### Valves Not Discovered
1. Check Zigbee2MQTT is running and connected
2. Verify MQTT base topic matches your setup
3. Use the `rescan` service
4. Add valve friendly names manually in options

### Flow Rate Shows 0
- Ensure valve is open and water is flowing
- Check if your device reports flow in different units
- Adjust flow scale in options if needed

### Session History Not Recording
- Verify Home Assistant recorder is enabled
- Check Home Assistant logs for errors

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## 🙏 Credits

Created for managing Sonoff SWV smart water valves in Home Assistant.
