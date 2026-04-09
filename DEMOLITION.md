# v4.0 demolition guide

> **Read before running.** This guide tears down the legacy v3.x
> helpers, template sensors, scripts, and automations that
> v4.0 replaced. Walk through each section in order. Stop at any
> step that doesn't match your install — the integration's own
> entities are NOT touched by anything in this guide.

After deploying v4.0 and running it in production for at least a
week, the legacy stack becomes dead weight. This guide is the
checklist for ripping it out cleanly. Every entity, script, and
automation listed here is something v4.0 absorbs into the integration
itself.

## Pre-flight

Before you start, verify the v4.0 stack is healthy:

- [ ] `sensor.z2m_irrigation_today_calculation` has a numeric state
      (not `unknown`) and shows your zones in attributes
- [ ] At least one schedule has been created and fired successfully
      (check `sensor.z2m_irrigation_schedule_history` — state should
      be ≥ 1)
- [ ] `sensor.z2m_irrigation_daily_totals` has data for the last
      few days
- [ ] The Hero card on the v4.0 dashboard shows the right state
      (running / scheduled / idle)
- [ ] You can manually trigger a smart cycle via
      `z2m_irrigation.run_smart_now` and the queue runner
      sequences zones correctly
- [ ] Panic + kill-switch flow has been smoke-tested at least once

If any of those fail, **stop here and fix them first**. Demolition
is a one-way operation; you don't want to be debugging v4.0 while
the legacy stack is also gone.

## Backup

Before demolishing anything:

```bash
# In your HA OS terminal addon
cp /config/configuration.yaml /config/configuration.yaml.pre-v4-demo
cp /config/automations.yaml /config/automations.yaml.pre-v4-demo
cp /config/scripts.yaml /config/scripts.yaml.pre-v4-demo
cp /config/scenes.yaml /config/scenes.yaml.pre-v4-demo
tar -czf /config/pre-v4-demo-snapshot.tar.gz \
  /config/configuration.yaml \
  /config/automations.yaml \
  /config/scripts.yaml \
  /config/.storage/core.config_entries \
  /config/.storage/lovelace*
```

If anything goes sideways you can roll back by restoring these files
and restarting HA. The integration's own state lives in
`.storage/z2m_irrigation.<entry_id>` and `z2m_irrigation.db` —
those are NOT touched by this guide.

---

## Stage 1 — disable, don't delete

For everything below, **disable first** and run for a few days.
Watch logs for unexpected references. Then come back and delete.
Disabling is reversible; deletion isn't.

### 1.1 Legacy automations

Open `automations.yaml`. Look for any automation that mentions:

- `service: switch.turn_on` with a Sonoff valve as the target
- `service: switch.turn_off` with a Sonoff valve
- `entity_id: input_boolean.irrigation_*`
- `entity_id: input_datetime.irrigation_*`
- `entity_id: timer.irrigation_*`
- A trigger that fires at irrigation times (e.g. `at: "06:00:00"`)
  and acts on a valve

For each match:

1. Add `enabled: false` at the top of the automation
2. Add a comment `# DEPRECATED v4.0 — replaced by z2m_irrigation.create_schedule`
3. Reload automations

Watch the logs. If nothing complains for 3 days, the automation is
truly dead and can be removed.

### 1.2 Legacy scripts

Open `scripts.yaml`. Look for any script that:

- Calls `switch.turn_on`/`turn_off` on a Sonoff valve
- Calls `mqtt.publish` to a `zigbee2mqtt/<valve>/set` topic
- Sets a `timer` for an irrigation duration
- Uses `repeat` to cycle through multiple valves

For each match:

1. Rename it from `irrigation_morning_cycle` (or similar) to
   `_DEPRECATED_irrigation_morning_cycle`
2. Reload scripts

Same waiting period — 3 days, then delete.

### 1.3 Legacy template sensors

Open `configuration.yaml` (and any `template:` files it includes).
Look for template sensors named:

- `sensor.irrigation_calculator_*`
- `sensor.irrigation_dryness_*`
- `sensor.irrigation_need_mm_*`
- `sensor.<zone>_liters_calculated`
- `sensor.<zone>_should_run`
- Anything that mentions `vpd`, `rain_today`, `forecast`, or
  `dryness` as a template input

For each one:

1. Comment it out (don't delete yet)
2. Reload templates (`developer-tools/yaml` → "Template Entities")
3. Watch the logs for "X is not available" warnings

### 1.4 Legacy input helpers

Settings → Devices & Services → **Helpers** tab. Look for:

- `input_boolean.irrigation_*` (manual run flags, smart-cycle toggles)
- `input_datetime.irrigation_*` (schedule times)
- `input_number.irrigation_*_factor` / `_l_per_mm` / `_base_mm`
- `input_select.irrigation_mode`
- `input_text.irrigation_*`
- `timer.irrigation_*`

For each one, click → **disable**. Don't delete yet.

---

## Stage 2 — verify nothing depends on the legacy entities

After disabling everything in Stage 1, run for **at least 3 days**
of normal operation including a few schedule fires. Then check:

```yaml
# Developer Tools → Template:
{% set legacy_entities = [
  'sensor.irrigation_calculator_total',
  'sensor.front_garden_liters_calculated',
  'input_boolean.irrigation_smart_mode',
  'timer.irrigation_morning',
  # ... add yours from Stage 1
] %}
{% for e in legacy_entities %}
  {{ e }}: {{ states(e) }}
{% endfor %}
```

Anything that returns a state means it's still loaded. Anything that
returns `unknown` is fully orphaned and safe to delete.

Also check the HA logs for the past 3 days for:

- "X has been registered before, declaring it untrusted"
- "Unable to find referenced entities X"
- "Template referenced X but it doesn't exist"

If any of those reference your legacy entities, something is still
calling them — find it and fix it before proceeding to Stage 3.

---

## Stage 3 — delete

Once Stage 2 is clean, remove the disabled items in this order:

### 3.1 Delete from configuration.yaml / automations.yaml / scripts.yaml

For each commented-out template sensor / automation / script from
Stage 1, delete the YAML block entirely. Reload after each file.

### 3.2 Delete helper entities

Settings → Devices & Services → Helpers. Delete each disabled
helper from Stage 1.4.

### 3.3 Delete dead Lovelace cards

If you had any `entities` cards or `markdown` cards that referenced
the deleted entities, edit them out of your dashboards. The v4.0
dashboard reads only `z2m_irrigation_*` entities and per-valve
sensors, so it stays unaffected.

### 3.4 Recorder cleanup (optional)

If your `configuration.yaml` had `recorder:` filters that excluded
`sensor.irrigation_*` patterns to keep DB size down, you can drop
those filter lines now — there are no `sensor.irrigation_*`
template sensors anymore. The integration's own entities use the
`z2m_irrigation_*` prefix and the per-valve `<friendly_name>_*`
naming, neither of which clashes with the legacy patterns.

---

## What v4.0 absorbed — quick reference

| Legacy thing | v4.0 replacement |
| --- | --- |
| Per-zone calculator template sensor | `sensor.z2m_irrigation_today_calculation` (with per-zone breakdown in attributes) |
| Per-zone `factor` / `l_per_mm` / `base_mm` input_numbers | `sensor.<zone>_zone_factor` / `_zone_l_per_mm` / `_zone_base_mm`, edited via `z2m_irrigation.set_zone_*` services |
| `input_boolean.irrigation_in_smart_cycle_<zone>` | `binary_sensor.<zone>_in_smart_cycle`, toggled via `z2m_irrigation.set_zone_in_smart_cycle` |
| `input_boolean.irrigation_master_enable` | `switch.z2m_irrigation_master_enable` |
| `input_boolean.irrigation_skip_today` | `z2m_irrigation.skip_today` / `clear_skip_today` services + `next_run_summary.skip_today` attribute |
| Time-of-day automation that calls `switch.turn_on` on each valve | `z2m_irrigation.create_schedule` (smart or fixed mode) + the engine's per-minute tick |
| `script.irrigation_morning_cycle` that walks through zones | `z2m_irrigation.run_smart_now` (one call, engine handles sequencing) |
| Per-zone `timer.irrigation_*` for run duration | The Sonoff SWV's native `cyclic_quantitative_irrigation` (volume) or `cyclic_timed_irrigation` (duration) — no HA-side timer needed |
| Template sensor that summed last-7-day usage | `sensor.z2m_irrigation_week_summary` |
| Template sensor that picked the next scheduled time | `sensor.z2m_irrigation_next_run_summary` |
| Template binary_sensor "is anything watering right now" | `binary_sensor.z2m_irrigation_any_running` |
| External pump-kill automation hooked to a custom event | `binary_sensor.z2m_irrigation_panic` + the `kill_switch_entity` config flow option |
| Recorder DB rows for legacy template sensor history | `sensor.z2m_irrigation_daily_totals` (reads the alpha-4 cache) + `sensor.<zone>_daily_history` |
| Lovelace dashboard built around legacy entities | `dashboards/z2m_irrigation.yaml` (alpha-5) |
| External pump-status notification | `binary_sensor.z2m_irrigation_panic` attributes + `EVENT_PANIC_REQUIRED` bus event |

If your legacy stack had a thing that doesn't appear in the table
above, **don't delete it yet**. Open an issue or check the v4.0
CHANGELOG entries; the integration may not have a 1:1 replacement
and you may want to keep the legacy thing alive.

---

## What NOT to touch

The following are integration-internal and must stay untouched
regardless of what you demolish:

- `/config/.storage/z2m_irrigation.<entry_id>` — the JSON config
  store with zones, schedules, history, daily summary cache.
- `/config/z2m_irrigation.db` — SQLite session history. The
  source of truth for all per-session data the dashboard renders.
- The Sonoff SWV valve devices in Settings → Devices & Services
  → Zigbee2MQTT. The integration discovers them by their
  friendly_name; renaming or removing them in Z2M will break the
  zone mapping.
- The integration's own Devices & Services entry — leave it alone
  unless you're uninstalling the entire integration.

---

## Rollback

If something breaks during demolition:

```bash
# Stop HA cleanly first via the UI: Settings → System → Restart
cp /config/configuration.yaml.pre-v4-demo /config/configuration.yaml
cp /config/automations.yaml.pre-v4-demo /config/automations.yaml
cp /config/scripts.yaml.pre-v4-demo /config/scripts.yaml
# Restart HA
```

The integration's JSON store and SQLite db are unaffected by
configuration.yaml / automations.yaml / scripts.yaml changes, so
your v4.0 schedules + history + per-zone config survive a rollback
intact.

---

## After demolition

You'll have:

- One integration entry (z2m_irrigation) under Settings → Devices
  & Services
- One dashboard (the v4.0 alpha-5 one) under Settings → Dashboards
- Two custom Lovelace cards auto-loaded
  (`custom:z2m-irrigation-embed-card` and
  `custom:z2m-irrigation-schedule-editor-card`)
- Per-valve devices visible under the integration with all their
  zone config + history sensors
- No `irrigation_*` helpers, template sensors, scripts, or
  automations in your config files

Total config-line reduction varies by setup, but typical savings are
500-1500 lines of YAML across `configuration.yaml` / `automations.yaml`
/ `scripts.yaml`. The integration absorbs the equivalent functionality
into ~7,500 lines of Python that v4.0 ships and HACS updates for you.

---

## Questions to answer before you demolish

Three questions worth pausing on:

1. **Are you happy with the v4.0 calculator's outputs?**  
   Compare `sensor.z2m_irrigation_today_calculation.attributes.zones`
   against whatever your legacy calculator was producing for the same
   day. If they're meaningfully different, the per-zone `factor` /
   `l_per_mm` / `base_mm` may need tweaking via the Setup tab BEFORE
   you delete the legacy template sensor that was producing the
   "right" answer.

2. **Are you happy with how the engine sequences multi-zone schedules?**  
   The engine's queue runner is strictly sequential (one valve at a
   time, with a 5-second inter-zone gap). If your legacy automations
   were running multiple zones in parallel for some reason — or with
   a longer gap — and you need that behavior preserved, the engine
   needs adjusting first. Open an issue.

3. **Is your kill switch wired up?**  
   Settings → Devices & Services → Z2M Irrigation → Configure → step
   3. If the `kill_switch_entity` is empty, the panic flow only fires
   the bus event and the persistent notification — there's no
   automatic upstream pump-kill. If your legacy stack had a separate
   automation listening for `EVENT_PANIC_REQUIRED` and killing a pump,
   you can either keep that automation OR move the entity into the
   integration's options flow and delete the automation.

If all three answer "yes" — proceed with Stage 1. If any answer is
"no" or "I'm not sure", fix the underlying thing first.
