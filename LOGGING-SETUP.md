# 📋 Logging Setup for Z2M Irrigation

## Making the Integration Appear in Logs Dropdown

To see **Z2M Irrigation** in the logs dropdown menu (like in your screenshot), you need to add it to your Home Assistant's logger configuration.

---

## Option 1: Using configuration.yaml (Recommended)

### Step 1: Edit configuration.yaml

Add this to your `/config/configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug
```

### Step 2: Check Configuration

```
Developer Tools → YAML → Check Configuration
```

### Step 3: Restart Home Assistant

```
Settings → System → Restart
```

### Step 4: Verify in Logs Dropdown

After restart, go to:
```
Settings → System → Logs → Dropdown (top right)
```

You should now see **"custom_components.z2m_irrigation"** in the list!

---

## Option 2: Using UI (Temporary - Resets on Restart)

### Step 1: Go to Logs

```
Settings → System → Logs
```

### Step 2: Filter

In the search box at top, type:
```
z2m_irrigation
```

### Step 3: View Integration Logs

You'll see all logs from the integration filtered.

**Note:** This method requires filtering each time. Option 1 makes it permanent and adds it to the dropdown.

---

## What You'll See

### Startup Logs
```
💾 Irrigation database: /config/z2m_irrigation.db
✅ Database tables created/verified
✅ Local irrigation database initialized
✅ Loaded totals for Water Valve 1: 0.00 L lifetime, 0.00 L resettable, 0.00 L (24h), 0.00 L (7d)
⚠️  Scheduler disabled in v3.0.0 - core irrigation tracking works fully locally
Starting ValveManager base=zigbee2mqtt manual=[] scale=1.0
```

### Session Logs
```
Starting volume run: Front Garden for 50.00 L (HA monitoring)
🚿 Starting session for Front Garden (Front Garden)
   Trigger: volume, Target: 50.0L / None min
📤 Creating session in Supabase: {...}
✅ Session created in Supabase: Front_Garden_1730510000.123
Volume run progress for Front Garden: 15.5/50.0 L (31.0%), flow: 8.2 L/min
🛑 Ending session: Front_Garden_1730510000.123
   Duration: 6.25 min, Volume: 50.12 L, Flow: 8.02 L/min
💾 Saved totals for Front Garden: +50.12L, +6.25min
✅ Updated totals:
   Lifetime: 50.12 L, 6.25 min
   Resettable: 50.12 L, 6.25 min
✅ Session ended: Front Garden - 6.25 min, 50.12 L, 8.02 L/min avg
```

---

## Advanced: Log Levels

### All Modules Debug Level
```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug
    custom_components.z2m_irrigation.manager: debug
    custom_components.z2m_irrigation.database: debug
    custom_components.z2m_irrigation.sensor: debug
    custom_components.z2m_irrigation.switch: debug
    custom_components.z2m_irrigation.number: debug
    custom_components.z2m_irrigation.websocket: debug
```

### Quiet Mode (Only Errors)
```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: error
```

### Production (Info Level)
```yaml
logger:
  default: warning
  logs:
    custom_components.z2m_irrigation: info
```

---

## Emoji Guide in Logs

The integration uses emojis to make logs easier to scan:

| Emoji | Meaning |
|-------|---------|
| 💾 | Database operations |
| ✅ | Success / Completed |
| ❌ | Error / Failed |
| ⚠️ | Warning / Notice |
| 🚿 | Session starting |
| 🛑 | Session ending |
| 🔍 | Loading data |
| 📤 | Saving data |
| 📊 | Updating totals |
| 🧹 | Cleanup operations |
| 🔄 | Reset operations |

---

## Troubleshooting

### Integration Not in Dropdown

**Problem:** After adding to configuration.yaml, integration still not in dropdown

**Solutions:**
1. Check configuration.yaml syntax (use Check Configuration)
2. Ensure proper indentation (YAML is indent-sensitive)
3. Restart Home Assistant (not just reload)
4. Clear browser cache
5. Try a different browser

### Example Bad YAML (Won't Work)
```yaml
logger:
default: info  # ❌ Wrong indentation
  logs:
custom_components.z2m_irrigation: debug  # ❌ Wrong indentation
```

### Example Good YAML (Will Work)
```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug
```

### No Logs Showing

**Problem:** Integration in dropdown but no logs

**Check:**
1. Is the integration loaded? (Settings → Devices → Integrations → Z2M Irrigation)
2. Are valves discovered? (Check entities)
3. Try triggering an action (start watering)

### Too Many Logs

**Problem:** Logs are overwhelming

**Solution:** Change to info level:
```yaml
logger:
  logs:
    custom_components.z2m_irrigation: info
```

Or just errors:
```yaml
logger:
  logs:
    custom_components.z2m_irrigation: error
```

---

## Log File Location

Logs are also written to:
```
/config/home-assistant.log
```

View with:
```bash
tail -f /config/home-assistant.log | grep z2m_irrigation
```

Or in File Editor add-on:
```
/config/home-assistant.log
```

---

## Complete configuration.yaml Example

Here's a complete logger configuration with MQTT and Z2M Irrigation:

```yaml
# Logger configuration
logger:
  default: info
  logs:
    # Z2M Irrigation (debug for troubleshooting)
    custom_components.z2m_irrigation: debug

    # MQTT (useful for debugging valve communication)
    homeassistant.components.mqtt: info

    # Zigbee2MQTT bridge (if needed)
    homeassistant.components.mqtt.client: warning

    # Other integrations (optional)
    homeassistant.components.sensor: warning
    homeassistant.components.switch: warning
```

---

## Viewing Specific Module Logs

### Only Database Operations
```yaml
logger:
  default: warning
  logs:
    custom_components.z2m_irrigation.database: debug
```

### Only Session Tracking
```yaml
logger:
  default: warning
  logs:
    custom_components.z2m_irrigation.manager: debug
```

### Only Sensor Updates
```yaml
logger:
  default: warning
  logs:
    custom_components.z2m_irrigation.sensor: debug
```

---

## Log Rotation

Home Assistant automatically rotates logs. Old logs saved as:
```
/config/home-assistant.log.1
/config/home-assistant.log.2
...
```

To increase retention, add to configuration.yaml:
```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug

recorder:
  purge_keep_days: 10  # Keep 10 days of history
```

---

## Getting Help

When reporting issues, please share logs with:

### Step 1: Enable Debug
```yaml
logger:
  logs:
    custom_components.z2m_irrigation: debug
```

### Step 2: Restart HA

### Step 3: Reproduce Issue

### Step 4: Copy Logs

Go to:
```
Settings → System → Logs → Search "z2m_irrigation"
```

Click **"Download"** or copy relevant section.

### Step 5: Share

Share logs on GitHub:
```
https://github.com/Zebra-zzz/z2m-irrigation/issues
```

**Remember to remove any sensitive info (names, addresses, etc.)**

---

## Summary

1. ✅ Add `custom_components.z2m_irrigation: debug` to configuration.yaml
2. ✅ Check configuration
3. ✅ Restart Home Assistant
4. ✅ Check logs dropdown - integration should appear!
5. ✅ Filter by "z2m_irrigation" to see all integration logs
6. ✅ Enjoy emoji-decorated, easy-to-read logs!

**The integration now shows all activity clearly with debug logging enabled by default in manifest.json!**
