# 🎨 Irrigation Controller Dashboard Setup

Complete guide to installing and configuring the irrigation controller dashboard for Z2M Irrigation v2.0+.

## 📋 Prerequisites

1. **Home Assistant** 2023.1 or newer
2. **Z2M Irrigation** v2.0.0 or newer installed
3. **Supabase** database configured
4. At least one Sonoff SWV valve connected

### Optional (Recommended)
- **Custom Button Card** (HACS) - For better button styling
- **Stack In Card** (HACS) - For grouped valve controls

## 🚀 Installation Steps

### Step 1: Install Helper Entities

You have two options:

#### Option A: Via UI (Recommended)

1. Go to **Settings** → **Devices & Services** → **Helpers**
2. Click **+ CREATE HELPER** and add each input manually using the values from `dashboard-helpers.yaml`

#### Option B: Via Configuration File

1. Open your `configuration.yaml`
2. Copy the entire contents of `dashboard-helpers.yaml`
3. Paste at the bottom of your `configuration.yaml`
4. **Restart Home Assistant**

### Step 2: Install Optional Custom Cards (Highly Recommended)

These make the dashboard look amazing:

1. Open **HACS** → **Frontend**
2. Search and install:
   - **Button Card**
   - **Stack In Card**
   - **Card Mod** (optional, for advanced styling)

3. Restart Home Assistant

### Step 3: Create the Dashboard

#### Method 1: New Dashboard (Recommended)

1. Go to **Settings** → **Dashboards**
2. Click **+ ADD DASHBOARD**
3. Name it: `Irrigation Controller`
4. Icon: `mdi:water`
5. Click **CREATE**
6. Click the ⋮ menu → **Edit Dashboard**
7. Click ⋮ again → **Raw Configuration Editor**
8. Delete everything and paste contents of `dashboard-irrigation-controller.yaml`
9. Click **SAVE**

#### Method 2: Add to Existing Dashboard

1. Open your existing dashboard
2. Click **Edit Dashboard**
3. Click **+ ADD VIEW**
4. Copy each view section from `dashboard-irrigation-controller.yaml`
5. Paste into raw editor for each new view

### Step 4: Customize Entity Names

The dashboard uses default entity names. Update these to match your setup:

**Find and Replace:**
- `water_valve_1` → Your actual valve 1 entity prefix
- `water_valve_2` → Your actual valve 2 entity prefix
- `water_valve_3` → Your actual valve 3 entity prefix
- `water_valve_4` → Your actual valve 4 entity prefix

**Valve Names to Update:**
- `Front Garden` → Your valve 1 name
- `Lilly Pilly` → Your valve 2 name
- `Back Garden` → Your valve 3 name
- `Mains Tap` → Your valve 4 name

### Step 5: Configure Quick Actions

Update the quick action buttons with your preferred durations/volumes:

```yaml
- type: button
  name: 5 Minutes  # Change this
  icon: mdi:timer
  tap_action:
    action: call-service
    service: z2m_irrigation.start_timed
    service_data:
      valve: Water Valve 1
      minutes: 5  # And this
```

## 📱 Dashboard Features

### Control Center Tab

**System Status Bar**
- System active indicator
- Total water used today
- Number of active schedules

**Valve Controls**
- Real-time status for each valve
- Battery and signal monitoring
- Current session info (flow, duration, remaining)
- Quick action buttons (5/15/30 min, custom liters)
- Emergency stop buttons

**Usage Statistics**
- Monthly usage per valve
- Historical trends

### Schedules Tab

**Schedule Management**
- Quick create buttons
- Active schedule cards with Run/Disable/Delete actions
- Live schedule status

**Time-Based Schedule Creator**
- Set name, valve, times
- Select specific days of week
- Choose duration or volume
- Add smart conditions

**Interval Schedule Creator**
- Set interval in hours
- Auto-repeat watering
- Duration or volume options

**Smart Conditions**
- Soil moisture sensor integration
- Temperature range limits
- Rain skip option

### History Tab

**Water Usage Charts**
- 7-day usage graph per valve
- Compare multiple valves
- Interactive timeline

**Session Statistics**
- Monthly session counts
- Average usage per session
- Total runtime

**Database Links**
- Direct links to Supabase tables
- View detailed session logs
- Schedule run history

### Settings Tab

**System Information**
- Signal quality for all valves
- Battery levels
- Connection status

**Maintenance**
- Reset all totals
- Rescan devices
- Database access

**Documentation**
- Links to guides
- Version information

## 🎯 Usage Guide

### Creating Your First Schedule

1. **Go to Schedules Tab**
2. **Fill out the form:**
   - Schedule Name: "Morning Lawn"
   - Valve: Water Valve 1
   - Run Type: duration
   - Duration: 15 minutes
3. **Set times:**
   - Time 1: 06:00
   - Leave Time 2 as 18:00 or clear it
4. **Select days:**
   - Enable Mon-Fri
   - Disable Sat-Sun
5. **Click "Create Time-Based Schedule"**

**You'll get a notification when it's created!**

### Getting Schedule IDs

After creating a schedule, you need its ID to manage it:

**Method 1: Check Supabase**
1. Open your Supabase dashboard
2. Go to **Table Editor** → `irrigation_schedules`
3. Find your schedule by name
4. Copy the `id` column value

**Method 2: Check Home Assistant Logs**
1. Go to **Settings** → **System** → **Logs**
2. Look for: `Added schedule 'Morning Lawn' (ID: abc123...)`

**Method 3: Via Developer Tools**
```yaml
service: z2m_irrigation.reload_schedules
```
Then check logs for loaded schedule IDs.

### Managing Schedules

Once you have the ID, update the schedule cards:

```yaml
- type: button
  name: Run Now
  icon: mdi:play
  tap_action:
    action: call-service
    service: z2m_irrigation.run_schedule_now
    service_data:
      schedule_id: "PASTE-YOUR-ID-HERE"
```

### Adding Smart Conditions

When creating a schedule:

1. **Scroll to "Smart Conditions"**
2. **For Soil Moisture:**
   - Enter sensor entity: `sensor.lawn_moisture`
   - Set max moisture: 50%
   - Skip watering if above 50%

3. **For Temperature:**
   - Min temp: 10°C (skip if colder)
   - Max temp: 35°C (skip if hotter)

4. **For Rain:**
   - Enable "Skip if Rained"
   - Requires weather integration

## 🎨 Customization

### Change Colors

Add to your `themes.yaml`:

```yaml
irrigation-theme:
  primary-color: "#2196F3"  # Blue for water
  accent-color: "#4CAF50"   # Green for active
  success-color: "#00C853"  # Bright green
  warning-color: "#FF9800"  # Orange
  error-color: "#F44336"    # Red
```

### Add More Valves

Copy a valve section and update:

```yaml
# Water Valve 5 - Greenhouse
- type: custom:stack-in-card
  mode: vertical
  cards:
    - type: horizontal-stack
      cards:
        - type: entity
          entity: switch.water_valve_5_valve
          name: Greenhouse
          # ... rest of config
```

### Custom Quick Actions

Add more duration options:

```yaml
- type: button
  name: 2 Minutes (Quick Test)
  icon: mdi:timer
  tap_action:
    action: call-service
    service: z2m_irrigation.start_timed
    service_data:
      valve: Water Valve 1
      minutes: 2
```

### Mobile View Optimization

The dashboard is responsive, but you can create mobile-specific views:

1. **Edit Dashboard**
2. **Click on view settings**
3. **Enable "Mobile Specific View"**
4. Use single-column layouts

## 🔧 Troubleshooting

### Dashboard Shows "Entity not found"

**Solution:** Update entity IDs to match your valves
```bash
# Find your actual entity IDs
Settings → Devices & Services → Z2M Irrigation → Your Valve
```

### Custom Cards Not Working

**Solution:** Install required HACS components
1. HACS → Frontend
2. Install: Button Card, Stack In Card
3. Clear browser cache (Ctrl+F5)
4. Restart Home Assistant

### Schedule Creation Does Nothing

**Solution:** Check helper entities exist
```bash
Developer Tools → States → Search "input_"
```
Should see all schedule inputs listed.

### Buttons Don't Work

**Solution:** Verify service names
```bash
Developer Tools → Services → Search "z2m_irrigation"
```
Should see all irrigation services.

### Script Errors

**Solution:** Check your `scripts:` section exists in `configuration.yaml`
```yaml
# In configuration.yaml
script: !include scripts.yaml

# OR if inline:
script:
  # paste scripts here
```

## 📊 Advanced Features

### Create Schedule Templates

Save common schedules as scripts:

```yaml
script:
  quick_morning_water:
    alias: Quick Morning Water All Zones
    sequence:
      - service: z2m_irrigation.run_schedule_now
        data:
          schedule_id: "morning-lawn-id"
      - delay: 00:20:00
      - service: z2m_irrigation.run_schedule_now
        data:
          schedule_id: "morning-garden-id"
```

### Auto-Disable in Rain

```yaml
automation:
  - alias: Disable Irrigation When Raining
    trigger:
      - platform: state
        entity_id: weather.home
        attribute: condition
        to: "rainy"
    action:
      - service: z2m_irrigation.disable_schedule
        data:
          schedule_id: "morning-lawn-id"
      - service: persistent_notification.create
        data:
          title: "Irrigation Paused"
          message: "Morning watering disabled due to rain"
```

### Weekly Reports

```yaml
automation:
  - alias: Weekly Irrigation Report
    trigger:
      - platform: time
        at: "20:00:00"
      - platform: time
        weekday: sun
    action:
      - service: notify.mobile_app
        data:
          title: "Weekly Irrigation Report"
          message: >
            This week's usage:
            Front: {{ states('sensor.water_valve_1_total') }}L
            Back: {{ states('sensor.water_valve_3_total') }}L
            Total: {{ (states('sensor.water_valve_1_total')|float +
                       states('sensor.water_valve_3_total')|float) | round(1) }}L
```

## 🎓 Best Practices

1. **Test Schedules First**
   - Use "Run Now" to test
   - Verify duration/volume
   - Check failsafes work

2. **Start Simple**
   - Create 1-2 schedules initially
   - Add conditions once stable
   - Monitor for a week before expanding

3. **Monitor Signal Quality**
   - Check Settings tab regularly
   - Low signal = unreliable valves
   - Reposition if needed

4. **Review History Weekly**
   - Check for skipped runs
   - Adjust conditions if too aggressive
   - Look for unexpected water usage

5. **Backup Your Config**
   - Export dashboard config monthly
   - Screenshot schedule IDs
   - Document your setup

## 🆘 Support

- **Issues:** https://github.com/Zebra-zzz/z2m-irrigation/issues
- **Discussions:** https://github.com/Zebra-zzz/z2m-irrigation/discussions
- **Documentation:** https://github.com/Zebra-zzz/z2m-irrigation

## 📝 Next Steps

1. ✅ Install helper entities
2. ✅ Create dashboard
3. ✅ Customize entity names
4. ✅ Create first schedule
5. ✅ Get schedule ID from Supabase
6. ✅ Update schedule cards
7. ✅ Test "Run Now"
8. ✅ Monitor first scheduled run
9. ✅ Add conditions once stable
10. ✅ Enjoy automated irrigation!

---

**Dashboard Version:** 2.0.0
**Last Updated:** 2025-10-20
**Compatible With:** Z2M Irrigation v2.0.0+
