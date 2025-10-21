# ⚡ Quick Start: Irrigation Persistence

## What's New

Your irrigation totals now **persist across restarts** and you have **lifetime totals that never reset**!

---

## 🆕 New Sensors

### Lifetime Totals (Never Reset)
```
sensor.water_valve_1_lifetime_total           # Total liters ever
sensor.water_valve_1_lifetime_total_minutes   # Total runtime ever
sensor.water_valve_1_lifetime_session_count   # Total sessions ever
```

### Resettable Totals (Existing)
```
sensor.water_valve_1_total                    # Resettable liters
sensor.water_valve_1_total_minutes            # Resettable runtime
sensor.water_valve_1_session_count            # Resettable count
```

---

## 🚀 Quick Setup

### 1. Restart Home Assistant
```bash
# Restart to load new sensors and Supabase persistence
Settings → System → Restart
```

### 2. Verify Sensors
Check that new sensors appear:
```
Developer Tools → States → Search "lifetime"
```

You should see:
- ✅ `sensor.water_valve_1_lifetime_total`
- ✅ `sensor.water_valve_1_lifetime_total_minutes`
- ✅ `sensor.water_valve_1_lifetime_session_count`

### 3. Add to Dashboard
```yaml
type: entities
title: Irrigation Totals
entities:
  # Lifetime (never reset)
  - entity: sensor.water_valve_1_lifetime_total
    name: "Total Water Used (All Time)"
  - entity: sensor.water_valve_1_lifetime_total_minutes
    name: "Total Runtime (All Time)"

  # Resettable (manual reset)
  - entity: sensor.water_valve_1_total
    name: "Water Used This Month"
  - entity: sensor.water_valve_1_total_minutes
    name: "Runtime This Month"
```

---

## 🔄 How It Works

### Before (Old System)
```
Home Assistant Restart → All totals reset to 0 ❌
No history preserved ❌
Data lost forever ❌
```

### After (New System)
```
Home Assistant Restart → Totals loaded from Supabase ✅
Complete history preserved ✅
Lifetime totals never reset ✅
Resettable totals only reset when you want ✅
```

---

## 🎮 Common Tasks

### Reset Monthly Totals
```yaml
# Manual reset
service: z2m_irrigation.reset_totals
data:
  topic: "Water Valve 1"  # Or omit to reset all
```

**Result:**
- ✅ Resettable totals reset to 0
- ✅ Lifetime totals **preserved**
- ✅ History remains intact

### Auto-Reset on 1st of Month
```yaml
automation:
  - alias: "Reset Irrigation Monthly"
    trigger:
      platform: time
      at: "00:00:01"
    condition:
      condition: template
      value_template: "{{ now().day == 1 }}"
    action:
      service: z2m_irrigation.reset_totals
```

### Check Persistence is Working
```bash
# 1. Note current totals
# 2. Restart Home Assistant
# 3. Check totals after restart
# Should be the same! ✅
```

---

## 📊 What's Stored

### In Supabase (Permanent)
- ✅ All session history
- ✅ Lifetime totals
- ✅ Resettable totals
- ✅ Daily statistics
- ✅ Complete audit trail

### Survives Restarts
- ✅ Yes! All data persists
- ✅ Automatically restored on startup
- ✅ No configuration needed

---

## 🔍 Verify It's Working

### Check Logs
```bash
cat /config/home-assistant.log | grep "irrigation"
```

**Should see:**
```
Session history initialized with Supabase persistence ✅
Loaded totals for Water Valve 1: 123.45 L lifetime, 45.67 L resettable ✅
```

**If you see:**
```
Supabase not configured - history will not persist ⚠️
```

**Fix:** Check `.env` file has:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
```

---

## 🎯 Quick Reference

| Action | Affects Resettable | Affects Lifetime |
|--------|-------------------|------------------|
| Irrigation session | ✅ Increases | ✅ Increases |
| `reset_totals` service | ✅ Resets to 0 | ❌ **Protected** |
| Home Assistant restart | ✅ **Persists** | ✅ **Persists** |
| Delete Supabase table | ⚠️ Data loss | ⚠️ Data loss |

---

## 💡 Pro Tips

### 1. Monthly Reset Automation
Set up automatic resets for monthly tracking:
```yaml
automation:
  - alias: "Reset on 1st"
    trigger:
      platform: time
      at: "00:00:01"
    condition:
      condition: template
      value_template: "{{ now().day == 1 }}"
    action:
      service: z2m_irrigation.reset_totals
```

### 2. High Usage Alert
Get notified when usage is high:
```yaml
automation:
  - alias: "High Usage Alert"
    trigger:
      platform: numeric_state
      entity_id: sensor.water_valve_1_total
      above: 100  # 100L threshold
    action:
      service: notify.mobile_app
      data:
        message: "High water usage: {{ states('sensor.water_valve_1_total') }} L"
```

### 3. Maintenance Reminder
Schedule maintenance based on lifetime usage:
```yaml
automation:
  - alias: "Valve Maintenance Due"
    trigger:
      platform: numeric_state
      entity_id: sensor.water_valve_1_lifetime_total
      above: 10000  # After 10,000L
    action:
      service: notify.mobile_app
      data:
        message: "Valve maintenance recommended at {{ states('sensor.water_valve_1_lifetime_total') }} L"
```

---

## ✅ Success Checklist

- [ ] Restarted Home Assistant
- [ ] New lifetime sensors appear in States
- [ ] Sensors show historical values (not 0)
- [ ] Logs show "Supabase persistence" message
- [ ] Tested reset (lifetime preserved)
- [ ] Tested restart (totals persist)
- [ ] Added lifetime sensors to dashboard
- [ ] Set up monthly reset automation

---

## 🆘 Troubleshooting

**Sensors show 0 after restart:**
- Check Supabase connection in logs
- Verify `.env` has correct credentials
- Restart Home Assistant again

**Lifetime totals got reset:**
- This should NEVER happen
- Check Supabase tables for data
- Contact support if data is lost

**Sessions not logging:**
- Check logs for "Session ended" messages
- Verify Supabase tables exist
- Run migration if tables missing

---

**You're all set! Your irrigation data is now permanent and safe!** 🎉

For detailed documentation, see: `PERSISTENCE-SYSTEM.md`
