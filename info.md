# Z2M Irrigation (Sonoff Valves)

Control and log Sonoff Zigbee water valves via Zigbee2MQTT with comprehensive session history tracking.

## Features

- **100% UI Configuration** - No YAML required
- **Multi-Valve Support** - Manage multiple valves from one integration
- **Real-Time Flow Monitoring** - Track water flow in L/min
- **Volume Tracking** - Precise litre integration with persistent totals
- **Smart Control Modes**:
  - Timed (auto-off after X minutes)
  - Volume (auto-off after X litres)
  - Manual (direct on/off)
- **GUI Session History** - Dedicated panel with filtering and CSV export
- **Automation Services** - Full HA automation support
- **Failsafe Protection** - Automatic retry and max runtime limits

## Quick Start

1. Install via HACS
2. Restart Home Assistant
3. Add integration: Settings → Devices & Services → Add Integration
4. Search for "Z2M Irrigation"
5. Configure your first valve

## Requirements

- Home Assistant 2024.1.0+
- MQTT integration configured
- Zigbee2MQTT with Sonoff water valves

## Documentation

Full documentation available in the [README](https://github.com/YOUR_USERNAME/ha-z2m-irrigation)
