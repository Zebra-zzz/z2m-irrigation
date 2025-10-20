# Installation Guide

## Quick Install

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots (⋮) → "Custom repositories"
4. Add repository URL: `https://github.com/YOUR_USERNAME/ha-z2m-irrigation`
5. Category: Integration
6. Click "Add"
7. Find "Z2M Irrigation (Sonoff Valves)" in HACS
8. Click "Download"
9. Restart Home Assistant
10. Go to **Settings** → **Devices & Services** → **Add Integration**
11. Search for "Z2M Irrigation"

### Manual Install

1. Download the latest release from GitHub
2. Extract files to your Home Assistant config directory:
   ```bash
   cd /config/custom_components
   # If you downloaded a release zip
   unzip z2m_irrigation.zip

   # Or clone the repository
   git clone https://github.com/YOUR_USERNAME/ha-z2m-irrigation.git z2m_irrigation
   ```
3. Restart Home Assistant
4. Go to **Settings** → **Devices & Services** → **Add Integration**
5. Search for "Z2M Irrigation"

## Directory Structure After Install

```
/config/
└── custom_components/
    └── z2m_irrigation/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── sensor.py
        ├── switch.py
        ├── websocket.py
        ├── logbook.py
        ├── manifest.json
        ├── services.yaml
        ├── strings.json
        ├── translations/
        │   └── en.json
        └── panel/
            └── panel.js
```

## Prerequisites

- Home Assistant 2024.1.0 or newer
- MQTT integration configured
- Zigbee2MQTT with Sonoff water valves paired

## First Time Setup

1. Add integration via UI
2. Configure first valve:
   - Name: e.g., "Garden Valve"
   - Topic: `zigbee2mqtt/Garden Valve` (must match Z2M friendly name)
   - Flow unit: Choose `lpm` or `m3h` based on your valve
   - Max runtime: 120 minutes (failsafe)
   - Noise floor: 0.3 L/min (tune if needed)

3. Check entities are created:
   - `switch.garden_valve`
   - `sensor.garden_valve_flow`
   - `sensor.garden_valve_total`
   - etc.

4. Access session history via sidebar: **Irrigation Sessions**

## Verify Installation

1. Check logs: **Settings** → **System** → **Logs**
   - Look for "Z2M Irrigation" entries
   - No errors should appear

2. Test valve control:
   - Toggle the switch entity
   - Watch Z2M logs for MQTT messages

3. Test services:
   ```yaml
   service: z2m_irrigation.start_timed
   data:
     name: "Garden Valve"
     minutes: 1
   ```

## Troubleshooting

### Integration Not Found

- Ensure `custom_components/z2m_irrigation/` exists
- Check file permissions (should be readable by HA)
- Restart HA and clear browser cache

### MQTT Not Working

- Verify MQTT integration is configured
- Check Z2M topic matches exactly (case-sensitive)
- Test with MQTT Explorer or HA Developer Tools → MQTT

### Entities Not Appearing

- Check Configuration → Integrations → Z2M Irrigation
- Look for error messages in logs
- Ensure valve topic is publishing data

## Updating

1. Download new version
2. Extract and replace files in `custom_components/z2m_irrigation/`
3. Restart Home Assistant
4. Clear browser cache

## Uninstalling

1. Remove integration via UI: Configuration → Integrations
2. Delete `custom_components/z2m_irrigation/` folder
3. Restart Home Assistant
4. Data persists in `.storage/z2m_irrigation_*` (delete manually if needed)
