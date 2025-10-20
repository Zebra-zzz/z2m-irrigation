# 📥 Installation Guide

## Prerequisites

- ✅ Home Assistant 2024.1.0 or newer
- ✅ MQTT integration configured
- ✅ Zigbee2MQTT running with Sonoff SWV valves paired

## Installation Methods

### 🎯 Via HACS (Recommended)

1. Open **HACS** in Home Assistant
2. Go to **"Integrations"**
3. Click **⋮** (three dots) → **"Custom repositories"**
4. Add repository:
   - **URL**: `https://github.com/Zebra-zzz/z2m-irrigation`
   - **Category**: Integration
5. Click **"Add"**
6. Find **"Z2M Irrigation (Sonoff Valves)"** in HACS
7. Click **"Download"**
8. **Restart Home Assistant**
9. Go to **Settings** → **Devices & Services** → **➕ Add Integration**
10. Search for **"Z2M Irrigation"**
11. Click to add the integration

### 📦 Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/Zebra-zzz/z2m-irrigation/releases)

2. Extract to your Home Assistant config directory:
   ```bash
   cd /config
   mkdir -p custom_components
   cd custom_components

   # Extract the downloaded zip
   unzip z2m_irrigation-1.0.0.zip

   # Or clone directly
   git clone https://github.com/Zebra-zzz/z2m-irrigation.git z2m_irrigation
   ```

3. **Restart Home Assistant**

4. Go to **Settings** → **Devices & Services** → **➕ Add Integration**

5. Search for **"Z2M Irrigation"**

## Directory Structure

After installation, you should have:

```
/config/
└── custom_components/
    └── z2m_irrigation/
        ├── __init__.py
        ├── config_flow.py
        ├── const.py
        ├── history.py
        ├── manager.py
        ├── number.py
        ├── sensor.py
        ├── switch.py
        ├── websocket.py
        ├── manifest.json
        ├── services.yaml
        └── strings.json
```

## Initial Setup

### 1. Add the Integration

1. Navigate to **Settings** → **Devices & Services**
2. Click **➕ Add Integration**
3. Search for "Z2M Irrigation"
4. Click to install

### 2. Configure Options (Optional)

Click the **⚙️ gear icon** on the integration to adjust:

- **MQTT Base Topic**: Default is `zigbee2mqtt` (change if yours differs)
- **Manual Valves**: Add friendly names manually if auto-discovery fails
- **Flow Scale**: Default `16.667` converts m³/h to L/min (usually no change needed)

### 3. Verify Entities Created

For each Sonoff SWV valve, you should see:

**Controls:**
- `switch.{valve_name}_valve`
- `number.{valve_name}_run_for_minutes`
- `number.{valve_name}_run_for_liters`

**Sensors:**
- `sensor.{valve_name}_flow`
- `sensor.{valve_name}_session_used`
- `sensor.{valve_name}_session_duration`
- `sensor.{valve_name}_remaining_time`
- `sensor.{valve_name}_remaining_liters`
- `sensor.{valve_name}_total`
- `sensor.{valve_name}_total_minutes`
- `sensor.{valve_name}_session_count`
- `sensor.{valve_name}_battery`
- `sensor.{valve_name}_link_quality`

## Testing the Installation

### Test Basic Control

1. Open **Developer Tools** → **States**
2. Find your valve switch entity
3. Toggle it ON and OFF
4. Watch for state changes

### Test Timed Run

```yaml
service: z2m_irrigation.start_timed
data:
  valve: "Garden Valve"  # Use your valve's friendly name
  minutes: 1
```

### Test Volume Run

```yaml
service: z2m_irrigation.start_liters
data:
  valve: "Garden Valve"
  liters: 10
```

### Check Logs

Go to **Settings** → **System** → **Logs**
- Look for entries starting with "Z2M Irrigation"
- No errors should appear during normal operation

## Troubleshooting

### ❌ Integration Not Found

**Problem**: Can't find integration when adding

**Solutions**:
- Verify `custom_components/z2m_irrigation/` folder exists
- Check file permissions (HA user must be able to read)
- Restart Home Assistant completely
- Clear browser cache (Ctrl+Shift+R)

### ❌ Valves Not Discovered

**Problem**: Integration loads but no valves appear

**Solutions**:
1. Check Zigbee2MQTT is running: `http://homeassistant.local:8080`
2. Verify MQTT integration is configured in HA
3. Confirm valve model is "SWV" in Z2M
4. Use `z2m_irrigation.rescan` service to force discovery
5. Add valve manually via integration options

### ❌ MQTT Connection Issues

**Problem**: Entities show as "unavailable"

**Solutions**:
- Verify MQTT broker is running
- Check MQTT integration configuration
- Test with **Developer Tools** → **MQTT** → Subscribe to `zigbee2mqtt/#`
- Ensure valve is paired and publishing to Z2M

### ❌ Flow Rate Always Zero

**Problem**: Flow sensor shows 0.0 L/min when valve is open

**Solutions**:
- Ensure water is actually flowing (check pressure)
- Verify valve's flow sensor is working in Z2M
- Check if your device reports flow in different units
- Adjust `flow_scale` in integration options if needed
- Some valves only report flow after a few seconds

### ❌ Config Flow 500 Error

**Problem**: Error when trying to add integration

**Solutions**:
- Check Home Assistant logs for detailed error
- Ensure no other instances of integration are running
- Restart Home Assistant
- Try clearing `.storage/core.config_entries` (backup first!)

## Updating the Integration

### Via HACS

1. Go to **HACS** → **Integrations**
2. Find "Z2M Irrigation"
3. Click **"Update"** if available
4. **Restart Home Assistant**

### Manual Update

1. Download new version
2. Replace files in `custom_components/z2m_irrigation/`
3. **Restart Home Assistant**
4. Clear browser cache

## Uninstalling

### Complete Removal

1. Go to **Settings** → **Devices & Services**
2. Find "Z2M Irrigation"
3. Click **⋯** → **Delete**
4. Delete the folder:
   ```bash
   rm -rf /config/custom_components/z2m_irrigation/
   ```
5. **Restart Home Assistant**

### Data Removal

Session history is stored in Home Assistant's recorder database:
- It will be automatically purged based on your recorder settings
- To manually clear, use the **Developer Tools** → **Statistics** section

## Getting Help

- 📖 [Full Documentation](README.md)
- 🐛 [Report Issues](https://github.com/Zebra-zzz/z2m-irrigation/issues)
- 💬 [Discussions](https://github.com/Zebra-zzz/z2m-irrigation/discussions)

---

**Version**: 1.0.0
**Last Updated**: October 2025
