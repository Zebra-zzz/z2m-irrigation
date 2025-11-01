# Debugging 24h/7d Entities Not Updating

## Step 1: Enable Debug Logging

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.z2m_irrigation: debug
    custom_components.z2m_irrigation.manager: debug
    custom_components.z2m_irrigation.database: debug
    custom_components.z2m_irrigation.sensor: debug
```

Then either:
- Restart Home Assistant, OR
- Go to Developer Tools → YAML → Reload "Logger"

## Step 2: Run a Test Irrigation Session

1. Turn on one of your valves (e.g., "Front Garden")
2. Let it run for at least 30 seconds
3. Turn it off

## Step 3: Check the Logs

Go to Settings → System → Logs and search for `z2m` or `24h` or `7d`

You should see detailed debug messages like:

```
🚿 Session started: Front Garden_1730512345.67 for Front Garden
💾 Saved totals for Front Garden: +5.50L, +2.00min
🔄 Updating time-based metrics for Front Garden
🔍 [24h] Querying usage for Front Garden since 2025-11-01T02:18:45
✅ [24h] Found Front Garden: 5.50L, 2.00min
   24h: 5.50L, 2.00min
🔍 [7d] Querying usage for Front Garden since 2025-10-25T03:18:45
✅ [7d] Found Front Garden: 5.50L, 2.00min
   7d: 5.50L, 2.00min
🛑 Session ended: Front Garden_1730512345.67 - 2.00min, 5.50L
```

## Step 4: Check the Database Directly

If you have SQLite browser access, you can check the database directly:

```bash
sqlite3 /config/z2m_irrigation.db "SELECT * FROM sessions ORDER BY started_at DESC LIMIT 5;"
```

This will show recent sessions with their timestamps and volumes.

## Common Issues to Look For

### Issue 1: Sessions Not Being Saved
If you don't see `🚿 Session started` and `🛑 Session ended` messages, then sessions aren't being tracked.

**Check:**
- Is the valve state changing from OFF → ON → OFF?
- Look for error messages about database writes

### Issue 2: Time-Based Queries Returning Zero
If you see `ℹ️ [24h] No sessions found` but you just ran water, the issue is with the database query.

**Check:**
- Are timestamps in UTC format?
- Are `ended_at` fields being set correctly?

### Issue 3: Entities Not Updating UI
If the database values are correct but UI doesn't update, it's a dispatcher issue.

**Check:**
- Look for `self._dispatch_signal(sig_update(v.topic))` in logs
- Check if sensor entities are properly subscribed to updates

## What to Share with Developer

If the issue persists, please share:

1. **Full debug logs** from a test irrigation session (from valve ON to valve OFF)
2. **Database content:**
   ```bash
   sqlite3 /config/z2m_irrigation.db "SELECT * FROM sessions WHERE valve_topic='Front Garden' ORDER BY started_at DESC LIMIT 3;"
   ```
3. **Entity states** from Developer Tools → States (search for `sensor.front_garden`)

## Quick Fix Attempt

If sessions are saving but 24h/7d entities show zero, try:

1. Reload the integration: Developer Tools → YAML → Reload "Z2M Irrigation"
2. Check if the entities now show correct values

This will force a fresh load from the database.
