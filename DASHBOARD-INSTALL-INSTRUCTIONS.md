# 📝 Dashboard Installation Instructions

Complete step-by-step guide for installing the irrigation dashboard with separate configuration files.

## 📦 Files Overview

You have 3 configuration files:

1. **`dashboard-helpers.yaml`** - Input helpers and template sensors (for configuration.yaml)
2. **`irrigation-scripts.yaml`** - Scripts for creating schedules (for scripts.yaml)
3. **`dashboard-irrigation-controller.yaml`** - Dashboard UI (for Home Assistant dashboard)

---

## 🚀 Installation Steps

### Step 1: Add Helpers to Configuration.yaml

Since your configuration.yaml already has this structure:
```yaml
automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
```

Add the helpers to your **configuration.yaml**:

**Option A: Direct Include (Recommended)**
```yaml
# Add this line to configuration.yaml
input_text: !include dashboard-helpers.yaml
input_select: !include dashboard-helpers.yaml
input_number: !include dashboard-helpers.yaml
input_datetime: !include dashboard-helpers.yaml
input_boolean: !include dashboard-helpers.yaml
template: !include dashboard-helpers.yaml
```

**Option B: Copy & Paste (Simpler)**
1. Open `dashboard-helpers.yaml`
2. Copy the **entire contents**
3. Paste at the bottom of your `configuration.yaml`
4. Save

### Step 2: Add Scripts to scripts.yaml

1. **Open your existing** `scripts.yaml` file
2. **Copy the contents** of `irrigation-scripts.yaml`
3. **Paste at the bottom** of your `scripts.yaml`
4. **Save**

**Your scripts.yaml should look like:**
```yaml
# Your existing scripts
existing_script_1:
  alias: Some Script
  ...

existing_script_2:
  alias: Another Script
  ...

# Irrigation scripts (paste from irrigation-scripts.yaml)
create_time_based_schedule:
  alias: Create Time-Based Schedule
  icon: mdi:calendar-plus
  mode: single
  sequence:
    - action: z2m_irrigation.create_schedule
      ...

create_interval_schedule:
  alias: Create Interval Schedule
  ...
```

### Step 3: Check Configuration & Restart

1. **Check Configuration:**
   - Go to **Developer Tools** → **YAML**
   - Click **"Check Configuration"**
   - Should show: "Configuration valid!"

2. **Restart Home Assistant:**
   - Settings → System → Restart
   - Wait for restart to complete

3. **Verify Helpers Exist:**
   - Go to **Developer Tools** → **States**
   - Search for `input_text.schedule_name`
   - Should see all the schedule inputs

4. **Verify Scripts Exist:**
   - Go to **Developer Tools** → **Services**
   - Search for `script.create_time_based_schedule`
   - Should see both create scripts

### Step 4: Create Dashboard

1. **Go to** Settings → Dashboards
2. **Click** "+ ADD DASHBOARD"
3. **Fill in:**
   - Name: `Irrigation Controller`
   - Icon: `mdi:water`
   - Show in sidebar: ✅ Yes
4. **Click CREATE**
5. **Click the ⋮ menu** → Edit Dashboard
6. **Click ⋮ again** → Raw Configuration Editor
7. **Delete all existing content**
8. **Copy entire contents** of `dashboard-irrigation-controller.yaml`
9. **Paste into the editor**
10. **Click SAVE**

### Step 5: Customize Entity Names

Update the dashboard to match your valve names:

**Find and Replace in dashboard:**
- `water_valve_1` → Your valve 1 entity ID
- `water_valve_2` → Your valve 2 entity ID
- `water_valve_3` → Your valve 3 entity ID
- `water_valve_4` → Your valve 4 entity ID

**Update friendly names:**
- `Front Garden` → Your valve 1 name
- `Lilly Pilly` → Your valve 2 name
- `Back Garden` → Your valve 3 name
- `Mains Tap` → Your valve 4 name

---

## ✅ Verification Checklist

After installation, verify everything works:

- [ ] Configuration check passes
- [ ] Home Assistant restarted successfully
- [ ] All input helpers visible in States
- [ ] Both scripts visible in Services
- [ ] Dashboard appears in sidebar
- [ ] Dashboard loads without errors
- [ ] Can see all valve entities
- [ ] Quick action buttons work
- [ ] Schedule creation form visible

---

## 📁 Alternative: Single File Setup

If you prefer everything in configuration.yaml:

1. **Open** `configuration.yaml`
2. **At the bottom**, paste contents of `dashboard-helpers.yaml`
3. **Also paste** contents of `irrigation-scripts.yaml` (under a `script:` section)
4. **Save and restart**

**Example:**
```yaml
# Your existing config
default_config:
automation: !include automations.yaml
script: !include scripts.yaml
...

# Paste dashboard-helpers.yaml contents here
input_text:
  schedule_name:
    name: Schedule Name
    ...

# If you don't have scripts included, add them directly:
script:
  create_time_based_schedule:
    alias: Create Time-Based Schedule
    ...
```

---

## 🔧 File Locations

Place files in your Home Assistant config directory:

```
/config/
├── configuration.yaml
├── scripts.yaml (your existing file)
├── automations.yaml
├── scenes.yaml
├── dashboard-helpers.yaml (copy contents to configuration.yaml)
└── irrigation-scripts.yaml (copy contents to scripts.yaml)
```

---

## 🆘 Troubleshooting

### "Configuration invalid" error

**Check for:**
1. Proper indentation (use spaces, not tabs)
2. No duplicate keys (e.g., two `script:` sections)
3. YAML syntax errors (colons, quotes)

**Fix:**
- Use the YAML validator in Developer Tools
- Check line numbers in error message
- Compare with original files

### Helpers not appearing

**Solution:**
1. Confirm they're in configuration.yaml
2. Check YAML syntax is correct
3. Restart Home Assistant
4. Check Developer Tools → States

### Scripts not working

**Solution:**
1. Confirm they're in scripts.yaml
2. Verify all scripts use `action:` not `service:`
3. Restart Home Assistant
4. Check Developer Tools → Services

### Dashboard shows "Entity not available"

**Solution:**
1. Update entity IDs in dashboard to match your valves
2. Check entity IDs in Developer Tools → States
3. Copy exact entity ID including prefix (e.g., `sensor.water_valve_1_flow`)

---

## 📚 Next Steps

After successful installation:

1. ✅ Test manual valve control (quick action buttons)
2. ✅ Create your first schedule via dashboard
3. ✅ Get schedule ID from Supabase
4. ✅ Update active schedule cards with real IDs
5. ✅ Test "Run Now" functionality
6. ✅ Monitor history and statistics

---

## 💡 Pro Tips

**Backup First:**
```bash
# Before making changes, backup your config
cp configuration.yaml configuration.yaml.backup
cp scripts.yaml scripts.yaml.backup
```

**Test Incrementally:**
1. Add helpers first, restart, verify
2. Then add scripts, restart, verify
3. Finally create dashboard

**Use Version Control:**
```bash
# If using Git
git add configuration.yaml scripts.yaml
git commit -m "Add irrigation dashboard"
```

---

**Installation Complete!** 🎉

You now have a fully functional irrigation controller dashboard!

**Need help?** Check DASHBOARD-SETUP.md for detailed configuration guide.
