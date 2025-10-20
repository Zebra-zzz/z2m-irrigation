# ⚡ Dashboard Quick Install (3 Steps)

## Step 1: Add to configuration.yaml (2 min)

**Copy entire contents** of `dashboard-helpers.yaml` and paste at the bottom of your `configuration.yaml`

```yaml
# Your existing configuration.yaml
default_config:
automation: !include automations.yaml
script: !include scripts.yaml
...

# PASTE dashboard-helpers.yaml CONTENTS HERE ↓
input_text:
  schedule_name:
    name: Schedule Name
    initial: "New Schedule"
    icon: mdi:form-textbox
  # ... rest of helpers ...
```

## Step 2: Add to scripts.yaml (1 min)

**Copy entire contents** of `irrigation-scripts.yaml` and paste at the bottom of your `scripts.yaml`

```yaml
# Your existing scripts.yaml
existing_script:
  alias: Some Script
  ...

# PASTE irrigation-scripts.yaml CONTENTS HERE ↓
create_time_based_schedule:
  alias: Create Time-Based Schedule
  icon: mdi:calendar-plus
  ...
```

## Step 3: Create Dashboard (2 min)

1. Settings → Dashboards → **+ ADD DASHBOARD**
2. Name: `Irrigation Controller`, Icon: `mdi:water`
3. Click **CREATE**
4. ⋮ → Edit Dashboard → ⋮ → **Raw Configuration Editor**
5. **Delete all**, paste `dashboard-irrigation-controller.yaml`
6. **SAVE**

---

## ✅ Check Configuration & Restart

```
Developer Tools → YAML → Check Configuration → ✅
Settings → System → Restart
```

---

## 🎯 Customize (5 min)

**Update entity IDs in dashboard:**
- Find: `water_valve_1` → Replace: Your valve entity
- Find: `Front Garden` → Replace: Your valve name

**Repeat for all valves (1, 2, 3, 4)**

---

## ✨ Done!

Go to **Irrigation Controller** in sidebar!

**See full guide:** `DASHBOARD-INSTALL-INSTRUCTIONS.md`
