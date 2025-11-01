# 🔧 Troubleshooting Guide

## Issue #1: Totals Reset on Restart

### Symptoms
- All totals (including lifetime) reset to 0 after restarting Home Assistant
- Session count resets to 0
- No persistence across restarts

### Root Cause
Supabase is not properly configured. The integration needs to connect to a **cloud Supabase database** to store data persistently.

### Solution

#### Step 1: Check .env File Location
The .env file MUST be in your Home Assistant config directory:
```bash
/config/.env  # If running in Docker/HassOS
# OR
~/.homeassistant/.env  # If running standalone
```

#### Step 2: Verify .env File Contents
Open the .env file and ensure it has these EXACT lines:
```bash
SUPABASE_URL=https://wldvztxlrejzvyjyzaym.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6IndsZHZ6dHhscmVqenZ5anl6YXltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjA5NDc2NDcsImV4cCI6MjA3NjUyMzY0N30._7FZozRveH2jNW-dr2R7HJk3EKl9q4RGsi9n4Xl-ARo
```

**CRITICAL:** The variable names must be exactly `SUPABASE_URL` and `SUPABASE_ANON_KEY` (NOT `VITE_SUPABASE_URL`)

#### Step 3: Restart Home Assistant
After fixing the .env file:
```
Settings → System → Restart
```

#### Step 4: Check Logs
After restart, check the logs for these messages:
```bash
# Go to: Settings → System → Logs → Search for "z2m_irrigation"

# ✅ GOOD - Should see:
✅ Session history initialized with Supabase persistence
   Supabase URL: https://wldvztxlrejzvyjyzaym.supabase.co
✅ Loaded persisted totals for Water Valve 1:
   Lifetime: 123.45 L, 45.67 min, 10 sessions
   Resettable: 23.45 L, 12.34 min, 3 sessions

# ❌ BAD - If you see:
❌ Supabase not configured - history will NOT persist across restarts!
   Config directory: /config
   Expected .env file at: /config/.env
   SUPABASE_URL found: False
   SUPABASE_ANON_KEY found: False
```

### Why Supabase is NOT Local
**Important:** Supabase is a **cloud database service** (like AWS RDS). It stores your data in the cloud, which means:
- ✅ Data survives Home Assistant restarts
- ✅ Data survives server crashes
- ✅ Data is backed up automatically
- ✅ Free tier available
- ❌ Requires internet connection

If you want a truly local solution, we would need to use SQLite or PostgreSQL running locally in Home Assistant.

---

## Issue #2: Session Remaining Sensors Not Populating

### Symptoms
- `sensor.water_valve_1_remaining_time` shows "Unknown" or 0
- `sensor.water_valve_1_remaining_liters` shows "Unknown" or 0
- This happens when using `z2m_irrigation.start_liters` service

### Root Cause
The session remaining sensors only populate when:
1. The valve is actually ON
2. A target has been set (liters or time)
3. Flow rate is being measured

### Debug Steps

#### Step 1: Check Valve is Actually ON
```yaml
# Check valve state in Developer Tools → States
sensor.water_valve_1.state  # Should be "ON"
```

#### Step 2: Check Target is Set
Look in the logs for:
```
Starting volume run: Water Valve 1 for 50.00 L (HA monitoring)
```

#### Step 3: Check Flow Rate
```yaml
# Check flow sensor
sensor.water_valve_1_flow.state  # Should be > 0 when water is flowing
```

**If flow is 0:**
- Valve may not be actually open
- Water pressure may be too low
- Flow sensor may be malfunctioning

#### Step 4: Check Session is Active
Look in logs for:
```
🚿 Starting session for Water Valve 1 (Water Valve 1)
   Trigger: volume, Target: 50.0L / None min
✅ Session created in Supabase: <session-id>
```

### Common Issues

#### Valve Turns ON but No Flow
1. Check physical valve - is it actually opening?
2. Check water pressure
3. Check for blockages

#### Flow Sensor Reports 0
1. Check Zigbee2MQTT logs for flow data
2. Verify valve device is sending flow measurements
3. Check `flow_scale` configuration (default: 1.0)

#### Session Never Starts
1. Check Home Assistant logs for errors
2. Verify Supabase connection (see Issue #1)
3. Check MQTT is working

---

## Issue #3: Automation Doesn't Populate Remaining Sensors

### Your Automation Analysis
Looking at your automation:
```yaml
action:
  - data:
      valve: Front Garden
      liters: "{{ front_liters|int }}"
    action: z2m_irrigation.start_liters
```

### Expected Behavior
1. Service `z2m_irrigation.start_liters` is called
2. Integration sets `target_liters` on valve
3. Integration sends MQTT command to turn valve ON
4. Valve reports state=ON via MQTT
5. Integration starts session
6. Remaining sensors populate

### What to Check

#### Check Service is Called
In logs, look for:
```
Starting volume run: Front Garden for 50.00 L (HA monitoring)
```

#### Check Valve Turns ON
In logs, look for:
```
🚿 Starting session for Front Garden (Front Garden)
   Trigger: volume, Target: 50.0L / None min
```

#### Check Flow Starts
In logs, look for:
```
Volume run progress for Front Garden: 5.2/50.0 L (10.4%), flow: 8.5 L/min
```

### Enable Full Debug Logging
The integration now has debug logging enabled by default. Check logs at:
```
Settings → System → Logs → Filter by "z2m_irrigation"
```

You should see emoji-decorated logs like:
- 🚿 = Session starting
- 🛑 = Session ending
- ✅ = Success
- ❌ = Error
- ⚠️ = Warning
- 🔍 = Loading data
- 📤 = Sending to Supabase
- 📊 = Updating totals

---

## Diagnostic Checklist

### Before Starting
- [ ] .env file exists in `/config/` directory
- [ ] SUPABASE_URL is set correctly
- [ ] SUPABASE_ANON_KEY is set correctly
- [ ] Home Assistant restarted after .env changes
- [ ] Logs show "Session history initialized with Supabase persistence"

### During Session
- [ ] Service call succeeds (check logs)
- [ ] Valve reports state=ON (check entity state)
- [ ] Flow rate > 0 (check sensor.xxx_flow)
- [ ] Session starts (check logs for 🚿 emoji)
- [ ] Session has valid ID (check logs)
- [ ] Remaining sensors update (check entity states)

### After Session
- [ ] Valve turns OFF when target reached
- [ ] Session ends successfully (check logs for 🛑 emoji)
- [ ] Totals updated in Supabase (check logs for ✅)
- [ ] Lifetime totals increased
- [ ] Resettable totals increased

---

## Common Error Messages

### "❌ Supabase not configured"
**Fix:** Set up .env file with correct credentials (see Issue #1)

### "⚠️ Session created in-memory only (no persistence)"
**Fix:** Supabase connection failed - check .env file and internet connection

### "⚠️ Session XXX not found in memory"
**Cause:** Session ended but trying to update again
**Impact:** Usually harmless, can ignore

### "❌ Failed to create session in Supabase - no result returned"
**Fix:** Check Supabase tables exist (run migrations)

### "FAILSAFE: Volume target reached for XXX"
**Cause:** Volume target met, forcing valve OFF
**Impact:** Normal operation, not an error

### "FAILSAFE: Backup timer expired for XXX"
**Cause:** Valve didn't turn off when expected
**Impact:** Safety feature activated, check valve operation

---

## Advanced Debugging

### View Supabase Data Directly

1. **Go to Supabase Dashboard**
   https://wldvztxlrejzvyjyzaym.supabase.co

2. **Check Tables**
   - `irrigation_valve_totals` - Should have rows for each valve
   - `irrigation_sessions` - Should have rows for each session
   - `irrigation_daily_stats` - Should have daily aggregates

3. **Query Sessions**
   ```sql
   SELECT *
   FROM irrigation_sessions
   ORDER BY started_at DESC
   LIMIT 10;
   ```

4. **Query Totals**
   ```sql
   SELECT *
   FROM irrigation_valve_totals;
   ```

### Enable Home Assistant SQL Queries
In configuration.yaml:
```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug
    homeassistant.components.mqtt: debug
```

### Check MQTT Messages
Use MQTT Explorer or mosquitto_sub:
```bash
mosquitto_sub -h localhost -t "zigbee2mqtt/Water Valve 1" -v
```

### Test Supabase Connection
Python test script:
```python
import aiohttp
import asyncio

async def test_supabase():
    url = "https://wldvztxlrejzvyjyzaym.supabase.co/rest/v1/irrigation_valve_totals"
    headers = {
        "apikey": "YOUR_ANON_KEY",
        "Authorization": "Bearer YOUR_ANON_KEY"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"Status: {resp.status}")
            print(await resp.json())

asyncio.run(test_supabase())
```

---

## Still Having Issues?

### Share Debug Logs
When reporting issues, please include:

1. **Full startup logs** (first 100 lines after restart)
2. **Session start logs** (when you call start_liters)
3. **Flow rate logs** (during watering)
4. **Session end logs** (when valve turns off)
5. **.env configuration** (hide the actual keys, just show if they exist)

### Log Format
```
Search for these emojis in logs:
🚿 - Session starts
🛑 - Session ends
✅ - Success operations
❌ - Errors
⚠️ - Warnings
🔍 - Data loading
📤 - Supabase requests
📊 - Total updates
```

### What to Check
- Home Assistant version
- Zigbee2MQTT version
- Valve model (should be Sonoff SWV)
- How valve was added (Z2M auto-discovery or manual)
- Internet connectivity
- Supabase region/latency

---

**Most common fix:** Restart Home Assistant after fixing .env file! 🔄
