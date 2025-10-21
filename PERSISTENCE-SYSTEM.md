# 🔒 Irrigation Persistence System

## Problem Solved

**BEFORE:** Every time you restarted Home Assistant, all your irrigation totals were reset to zero. You lost all history of water usage, runtime, and session counts.

**NOW:** All irrigation data is permanently stored in Supabase and automatically restored after every restart. You'll never lose your data again!

---

## 🎯 Key Features

### 1. **Lifetime Totals (NEVER Reset)**
These sensors track your irrigation usage since installation and **cannot be reset**:

- `sensor.water_valve_1_lifetime_total` - Total liters since installation
- `sensor.water_valve_1_lifetime_total_minutes` - Total runtime since installation
- `sensor.water_valve_1_lifetime_session_count` - Total sessions since installation

**Use Case:** Track long-term water usage for billing, conservation, or maintenance scheduling.

### 2. **Resettable Totals (Manual Reset)**
These sensors can be reset manually when you call the `z2m_irrigation.reset_totals` service:

- `sensor.water_valve_1_total` - Resettable total liters
- `sensor.water_valve_1_total_minutes` - Resettable total runtime
- `sensor.water_valve_1_session_count` - Resettable session count

**Use Case:** Track monthly/seasonal usage. Reset at the start of each month or season.

### 3. **Complete Session History**
Every single irrigation session is logged with:
- Start and end times
- Duration and volume used
- Average flow rate
- How it was triggered (manual, schedule, automation)
- Whether it completed successfully

**Use Case:** Audit trail, troubleshooting, usage analysis, billing verification.

### 4. **Daily Statistics**
Automatic daily aggregation of:
- Total water used per day
- Total runtime per day
- Session count per day
- Average flow rate per day

**Use Case:** Charts, graphs, trend analysis, daily reports.

---

## 📊 Database Tables

### `irrigation_valve_totals`
Stores current totals for each valve:
```sql
CREATE TABLE irrigation_valve_totals (
  valve_topic text PRIMARY KEY,
  valve_name text NOT NULL,

  -- Lifetime totals (NEVER reset)
  lifetime_total_liters numeric(12,2),
  lifetime_total_minutes numeric(12,2),
  lifetime_session_count integer,

  -- Resettable totals
  resettable_total_liters numeric(12,2),
  resettable_total_minutes numeric(12,2),
  resettable_session_count integer,

  last_reset_at timestamptz,
  created_at timestamptz,
  updated_at timestamptz
);
```

### `irrigation_sessions`
Complete history of every session:
```sql
CREATE TABLE irrigation_sessions (
  id uuid PRIMARY KEY,
  valve_topic text NOT NULL,
  valve_name text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  duration_minutes numeric(10,2),
  volume_liters numeric(10,2),
  avg_flow_rate numeric(8,2),
  trigger_type text,
  target_liters numeric(10,2),
  target_minutes numeric(10,2),
  completed_successfully boolean,
  notes text
);
```

### `irrigation_daily_stats`
Daily aggregated statistics:
```sql
CREATE TABLE irrigation_daily_stats (
  date date NOT NULL,
  valve_topic text NOT NULL,
  total_liters numeric(10,2),
  total_minutes numeric(10,2),
  session_count integer,
  avg_flow_rate numeric(8,2),
  PRIMARY KEY (date, valve_topic)
);
```

---

## 🔄 How It Works

### On Startup
1. Integration discovers valves from Zigbee2MQTT
2. For each valve, queries Supabase for persisted totals
3. Loads lifetime and resettable totals into memory
4. Sensors immediately show correct historical values

### During Session
1. When valve turns ON → Creates session record in Supabase
2. While running → Tracks flow, liters, duration in memory
3. When valve turns OFF → Updates session with final values
4. Updates both lifetime and resettable totals in Supabase
5. Updates daily statistics for today
6. Syncs all values back to Home Assistant sensors

### On Reset
1. User calls `z2m_irrigation.reset_totals` service
2. System updates Supabase to zero out resettable totals
3. **Lifetime totals remain unchanged** (protected)
4. Syncs new values to Home Assistant
5. `last_reset_at` timestamp updated

---

## 🎮 How to Use

### View Lifetime Totals
```yaml
# Example dashboard card
type: entities
entities:
  - entity: sensor.water_valve_1_lifetime_total
    name: "Total Water Used (All Time)"
  - entity: sensor.water_valve_1_lifetime_total_minutes
    name: "Total Runtime (All Time)"
  - entity: sensor.water_valve_1_lifetime_session_count
    name: "Total Sessions (All Time)"
```

### View Resettable Totals
```yaml
type: entities
entities:
  - entity: sensor.water_valve_1_total
    name: "Water Used This Month"
  - entity: sensor.water_valve_1_total_minutes
    name: "Runtime This Month"
  - entity: sensor.water_valve_1_session_count
    name: "Sessions This Month"
```

### Reset Monthly Totals
```yaml
# Automation to reset on 1st of each month
automation:
  - alias: "Reset Irrigation Totals Monthly"
    trigger:
      - platform: time
        at: "00:00:01"
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"
    action:
      - service: z2m_irrigation.reset_totals
        data:
          topic: "Water Valve 1"  # Or omit to reset all valves
```

### Query Session History (Developer Tools)
```python
# Get recent sessions for a valve
history.get_recent_sessions("Water Valve 1", limit=50)

# Get daily stats for last 30 days
history.get_daily_stats("Water Valve 1", days=30)
```

---

## 🔐 Data Safety

### Automatic Backups
- Supabase provides automatic daily backups
- Point-in-time recovery available
- No data loss from Home Assistant restarts

### Dual Storage
- **Supabase:** Permanent, persistent storage
- **Home Assistant Memory:** Fast access for real-time updates
- **Synchronization:** Automatic bidirectional sync

### Protected Data
- **Lifetime totals:** Cannot be reset (permanent record)
- **Sessions:** Append-only (never deleted automatically)
- **Daily stats:** Immutable historical records

---

## 📈 Example Queries

### Total Water Usage Since Installation
```sql
SELECT
  valve_name,
  lifetime_total_liters,
  lifetime_total_minutes
FROM irrigation_valve_totals
ORDER BY lifetime_total_liters DESC;
```

### Sessions This Month
```sql
SELECT
  valve_name,
  started_at,
  duration_minutes,
  volume_liters,
  trigger_type
FROM irrigation_sessions
WHERE started_at >= date_trunc('month', CURRENT_DATE)
ORDER BY started_at DESC;
```

### Daily Usage Trend
```sql
SELECT
  date,
  valve_name,
  total_liters,
  session_count
FROM irrigation_daily_stats
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC, valve_name;
```

### Average Session Duration
```sql
SELECT
  valve_name,
  ROUND(AVG(duration_minutes), 2) as avg_duration,
  ROUND(AVG(volume_liters), 2) as avg_volume,
  COUNT(*) as total_sessions
FROM irrigation_sessions
WHERE ended_at IS NOT NULL
GROUP BY valve_name;
```

---

## 🚨 Troubleshooting

### Totals Not Persisting
**Check Supabase configuration:**
```bash
# View Home Assistant logs
cat /config/home-assistant.log | grep "Supabase"

# Should see:
# "Session history initialized with Supabase persistence"
# "Loaded persisted totals for..."
```

**Verify environment variables:**
- `SUPABASE_URL` must be set in `.env`
- `SUPABASE_ANON_KEY` must be set in `.env`

### Totals Reset on Restart
If totals reset to zero after restart, Supabase may not be configured:
1. Check `.env` file has correct values
2. Restart Home Assistant
3. Check logs for "Supabase not configured" warning

### Session History Empty
If `history.get_recent_sessions()` returns empty:
1. Verify sessions are being created (check logs)
2. Check Supabase dashboard → `irrigation_sessions` table
3. Verify RLS policies allow public read access

---

## 📋 Best Practices

### 1. Regular Resets
Reset resettable totals at regular intervals:
- **Monthly:** For billing cycles
- **Seasonally:** For spring/summer tracking
- **Weekly:** For detailed analysis

### 2. Monitor Lifetime Totals
Watch lifetime totals for:
- **Maintenance scheduling** (e.g., replace valve at 10,000 L)
- **Leak detection** (unexpected increases)
- **System health** (declining flow rates)

### 3. Review Session History
Check session history for:
- **Failed sessions** (`completed_successfully = false`)
- **Abnormal durations** (too short or too long)
- **Flow rate anomalies** (clogged lines, leaks)

### 4. Create Alerts
```yaml
automation:
  - alias: "Alert: High Daily Water Usage"
    trigger:
      - platform: time
        at: "21:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.water_valve_1_total
        above: 100  # 100L threshold
    action:
      - service: notify.mobile_app
        data:
          message: "High water usage today: {{ states('sensor.water_valve_1_total') }} L"
```

---

## 🎯 Summary

**What Changed:**
- ✅ Added 3 new lifetime total sensors (never reset)
- ✅ Totals now persist across Home Assistant restarts
- ✅ Complete session history logged to Supabase
- ✅ Daily statistics automatically aggregated
- ✅ Reset service only resets resettable totals
- ✅ Lifetime totals are protected and permanent

**What Stayed the Same:**
- ✅ Existing sensors still work (`total`, `total_minutes`, `session_count`)
- ✅ Reset service still works (but now preserves lifetime data)
- ✅ All existing automations and dashboards work unchanged

**What to Do:**
1. ✅ Restart Home Assistant to load new sensors
2. ✅ Add lifetime total sensors to your dashboard
3. ✅ Create monthly reset automation
4. ✅ Enjoy never losing your data again!

---

**Your irrigation data is now safe, permanent, and comprehensive!** 🎉
