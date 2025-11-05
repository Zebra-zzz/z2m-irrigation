# Push to GitHub Instructions

All fixes are ready and committed locally. To push to GitHub:

## Option 1: Direct Push (Recommended)
```bash
cd /path/to/your/local/z2m-irrigation/repo
git pull origin main  # Get latest changes
cp -r /tmp/cc-agent/58886398/project/custom_components/z2m_irrigation/* custom_components/z2m_irrigation/
cp /tmp/cc-agent/58886398/project/CHANGELOG.md .
cp /tmp/cc-agent/58886398/project/README.md .
git add .
git commit -m "Fix critical race conditions in session tracking and sensor initialization (v3.0.1)

This release fixes two critical race conditions that were causing data integrity issues:

1. Session ID Capture Bug
   - Session IDs were being cleared before async database operations completed
   - Resulted in session_id=None in logs and NULL ended_at in database
   - Fixed by capturing all session values in local variables before clearing
   - Ensures complete session records in database

2. Sensor Initialization Race
   - Sensors were created before valve data loaded from database
   - Caused sensors to briefly show 0.0 on restart before updating
   - Fixed by loading all metrics BEFORE announcing valve to sensor platform
   - Sensors now show correct values immediately on startup

Changes:
- custom_components/z2m_irrigation/manager.py:
  - _ensure_valve(): Load data before creating sensors
  - _on_state(): Capture session values before async operations
- CHANGELOG.md: Added v3.0.1 release notes
- README.md: Updated to v3.0.1
- manifest.json: Bumped version to 3.0.1"
git push origin main
```

## Option 2: Copy Files Directly
The fixed files are in `/tmp/cc-agent/58886398/project/`

Key files changed:
- `custom_components/z2m_irrigation/manager.py` - Both race conditions fixed
- `custom_components/z2m_irrigation/manifest.json` - Version bumped to 3.0.1
- `CHANGELOG.md` - Added v3.0.1 release notes
- `README.md` - Updated version and description

## What Was Fixed

### 1. Session ID Race Condition (Lines 257-302 in manager.py)
**Problem:** `v.current_session_id` was cleared before `_end_and_sync()` executed, causing `session_id=None`

**Solution:** Capture session values in local variables before clearing:
```python
captured_session_id = v.current_session_id
captured_session_liters = v.session_liters
# ... then use captured values in async function
```

### 2. Sensor Initialization Race (Lines 139-171 in manager.py)
**Problem:** Sensors created before database loaded, showing 0.0 temporarily

**Solution:** Moved `self._dispatch_signal(SIG_NEW_VALVE, v)` INSIDE async function, AFTER data loads:
```python
async def _sub_and_load():
    # 1. Subscribe to MQTT
    # 2. Load ALL data from database
    # 3. THEN announce valve (creates sensors with correct values)
```

## After Push
Users can update via HACS. They should see:
- ✅ Sessions properly tracked with complete records
- ✅ Sensors show correct values on restart (no more 0.0 flash)
- ✅ All 24h/7d metrics accurate
- ✅ Database integrity maintained
