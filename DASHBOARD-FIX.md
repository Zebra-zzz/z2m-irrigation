# Dashboard Helpers - Error Fix

## Issue
The `dashboard-helpers.yaml` file was causing errors:
```
String does not match the pattern of "LEGACY_SYNTAX"
```

## Cause
Home Assistant 2024+ requires using `action:` instead of `service:` in script sequences.

## Fix Applied
Changed all instances of:
```yaml
- service: z2m_irrigation.create_schedule
```

To:
```yaml
- action: z2m_irrigation.create_schedule
```

## Changes Made
1. ✅ Line 173: `create_time_based_schedule` - Changed `service:` to `action:`
2. ✅ Line 234: Notification in time-based script - Changed `service:` to `action:`
3. ✅ Line 244: `create_interval_schedule` - Changed `service:` to `action:`
4. ✅ Line 273: Notification in interval script - Changed `service:` to `action:`

## Status
✅ **FIXED** - All service calls now use the modern `action:` syntax

## How to Apply
1. Replace your `dashboard-helpers.yaml` with the fixed version
2. Restart Home Assistant
3. Check Configuration → Check configuration validity
4. Should show no errors now!

## Verification
Run this to verify no more `service:` references:
```bash
grep "service:" dashboard-helpers.yaml
```
Should return nothing (or only in comments).

---

**Fixed on:** 2025-10-20
**Compatible with:** Home Assistant 2024.1+
