# Changelog

All notable changes to the Z2M Irrigation integration will be documented in this file.

## [4.0.0rc3] - 2026-04-09

### 🐛 v4.0 release candidate 3 — UX gaps from the live soak

Three real issues found during the rc-2 soak and fixed in rc-3:

#### B5 — `last_session_liters` not persisted across HA restart

`Valve.last_session_liters` is set in `_end_and_sync` after a session
ends, but it was **never loaded from the SQLite database on startup**.
After every HA restart, the field stayed `None` until the next session
ended, so the per-zone tile metric showed `— L` for hours/days even
though the session history had the data.

**Fix in `database.py`**: new `IrrigationDatabase.get_last_session(valve_topic)`
method that returns the most recent completed session row for one valve
(volume_liters, duration_minutes, started_at, ended_at, trigger_type,
target_liters, target_minutes).

**Fix in `manager.py`**: `_ensure_valve._sub()` now calls
`db.get_last_session()` alongside the existing 24h/7d aggregate loads
and populates `valve.last_session_liters` from the result. Logged at
INFO level: `B5: hydrated last_session_liters for <zone> = X.XX L`.

After deploying rc-3 + restarting HA once, every zone tile should
show its real last-run liters immediately on cold start.

#### F-I — Session Log tab

User asked for a Log tab showing all runs in a table with start/stop
times, trigger type, starting parameters, and final delivered values.
All this data already lives in the SQLite `sessions` table — just
needed to be exposed as an HA entity and rendered.

**New backend method** in `database.py`:
`get_recent_sessions(limit=200, valve_topic=None)` — returns the most
recent N completed sessions newest-first, optionally filtered to one
valve. Each row carries: session_id, valve, name, started_at, ended_at,
duration_minutes, volume_liters, avg_flow_lpm, trigger_type,
target_liters, target_minutes, completed_successfully.

**New global sensor** `sensor.z2m_irrigation_session_log`:
* State = total session count in the buffer (≤ 200)
* Attributes: `sessions[]` array of dicts (most-recent first), `limit`
* Refreshed on `async_added_to_hass` and every 5 minutes via
  `async_track_time_interval`. The 5-min cadence is faster than the
  manager's 15-min metric loop because session-end timing is when the
  user is most likely to be looking at the Log tab.

**New "Log" tab** in the dashboard (5th view): markdown card with
Jinja that renders the most recent 50 sessions as a table with columns
**When · Zone · Trigger · Target · Delivered · Duration · Avg flow · OK**.
Trailing rows beyond 50 stay in the buffer attribute but are not
rendered (HA markdown card has implicit size limits). Buffer cap is
200 entries total.

#### F-J — Schedule editor card edit/delete

The user reported they could create schedules from the dashboard but
had no way to edit or delete them — they had to call
`z2m_irrigation.update_schedule` / `delete_schedule` from Developer
Tools with the schedule_id.

**Editor card upgrade** (`z2m-irrigation-schedule-editor-card.js`,
version bumped to `4.0.0rc3`):

* New "existing schedules" list at the top of the card, populated
  from `sensor.z2m_irrigation_schedules.attributes.schedules`. One row
  per schedule with the name + enabled/disabled badge, time, days,
  mode, zone count, and last run outcome.
* Per-row **Edit** button: pre-fills the form with the schedule's
  current values and switches the form into edit mode (form title
  changes to `Editing: <name>`, submit button label changes from
  `Create schedule` to `Save changes`).
* Per-row **Delete** button: shows a `window.confirm` dialog and
  calls `z2m_irrigation.delete_schedule` with the schedule_id.
* New `_form.editing_id` field — null in CREATE mode, set to the
  schedule_id when editing. The submit handler routes to either
  `update_schedule` or `create_schedule` based on this flag.
* `_loadScheduleForEdit(schedule_id)` reads the schedule from the
  sensor cache and pre-fills every field including the chip
  selectors for days and zones.
* `_deleteSchedule(schedule_id, name)` shows the confirm dialog and
  calls the delete service.
* The reset button label changes from "Reset form" to "Cancel edit"
  in edit mode and restores create mode on click.
* New CSS for the schedule list (`.sched-row`, `.sched-info`,
  `.sched-actions`, `.btn-mini.btn-edit`, `.btn-mini.btn-delete`,
  `.badge`, `.divider`).
* `set hass(hass)` now also re-renders when the schedules sensor's
  attributes change (after a CREATE / UPDATE / DELETE service call
  lands), not just on zones change.

#### Backward compatibility

- v3.2.1 through v4.0-rc-2 behaviour is preserved end-to-end. All
  rc-3 changes are additive.
- The new `database.get_last_session` and `get_recent_sessions`
  methods don't modify the SQLite schema or any existing data —
  they're pure reads using the existing `idx_sessions_ended` index.
- The new `SessionLogSensor` is opt-in via the dashboard. If you
  don't import the new dashboard YAML, the sensor still loads but
  nothing renders it.
- The schedule editor card edit/delete features are additive — the
  existing CREATE flow continues to work unchanged. Edit mode is
  only entered when the user explicitly clicks an Edit button on
  an existing schedule row.

#### What's still pending in v4.0

- **F-B** — sun-relative schedule times (sunrise-45m etc) — v4.1
- **F-G** — VPD time-of-day sampling bias (24h average) — v4.1
- **F-H** — backend rename `l_per_mm` → `area_m2`, `base_mm` →
  `water_per_day_mm` (rc-4 candidate, schema migration v1 → v2)
- **B3** — reconcile `unique_id` ↔ `friendly_name` mismatch on global
  sensors (causes the entity_id slugs to drop the `_summary` suffix
  the unique_id implies). Cosmetic, deferred.
- **B4** — delete stale `.storage/z2m_irrigation.<old_entry_id>` file
  from a previous config-entry. Cleanup, deferred.
- **F-A polish** — auto-add a 5th valve to the dashboard without
  needing YAML edits. Requires a custom JS card for per-zone tiles
  that doesn't depend on auto-entities. v4.1 candidate.

## [4.0.0rc2] - 2026-04-09

### 🐛 v4.0 release candidate 2 — unit-aware weather conversion

Hotfix on top of rc1, found during the first live deploy soak. The
calculator was reading VPD raw without checking the source sensor's
unit_of_measurement, treating an Ecowitt GW2000C reading of `9.38 hPa`
as if it were `9.38 kPa`. That slammed the dryness factor against its
1.5 ceiling and inflated the daily total by ~60% (172.8L instead of
the correct ~108L on that day's weather).

The fix is in `weather.py`: each calculator input is now read via a
unit-aware path that consults the entity's `unit_of_measurement`
attribute and applies a conversion factor to the target unit (kPa for
VPD, mm for rain). Unknown units pass through with a warning so the
user is told what to fix instead of getting silently incorrect numbers.

#### What changed

- **`weather.py`** rewritten with unit-aware conversion. Two new
  conversion tables:
  - `_PRESSURE_TO_KPA` — covers kpa, hpa, mbar, pa, bar, psi, atm,
    mmhg, inhg. Most common in the wild are `hpa` (Ecowitt, BoM,
    OpenWeatherMap default) and `kpa` (some custom template helpers,
    AccuWeather).
  - `_LENGTH_TO_MM` — covers mm, cm, m, in, inch, inches, `"`, ft.
    Most common in the wild are `mm` (every weather provider outside
    the US) and `in` / `inches` (US weather stations like AmbientWeather
    and Weather Underground).
- **New helpers**:
  - `_read_float_raw(hass, entity_id)` — returns `(value, normalized_unit)`
    or `None`. Pulled out so the unit-aware path and the legacy
    pass-through can share the parsing + null-handling.
  - `_convert_via_table(entity_id, parsed, table, target_label)` — applies
    a conversion table; passes through with a warning on unknown unit
    or missing unit. Logs are deduplicated naturally by HA's logger.
  - `_read_pressure_kpa(hass, entity_id)` — convenience wrapper.
  - `_read_length_mm(hass, entity_id)` — convenience wrapper.
- **`_read_float`** is preserved unchanged for the display-only
  `temp_c` field where HA already standardizes °C across integrations
  and the calculator doesn't act on the value.
- **`read_inputs`** now calls `_read_pressure_kpa(vpd_entity)`,
  `_read_length_mm(rain_today_entity)`, and
  `_read_length_mm(rain_forecast_24h_entity)`.
- **No config flow change** — the user's existing entity selections
  keep working unchanged. The conversion happens transparently inside
  the integration.

#### Conversion table coverage

The most common real-world cases are now covered without any user
action required:

| Source provider | Native VPD unit | Native rain unit | Works in rc-2 |
| --- | --- | --- | --- |
| Ecowitt GW2000C | hPa | mm | ✅ |
| BoM Australia | (no native VPD) | mm | ✅ for rain |
| OpenWeatherMap | hPa | mm | ✅ |
| AccuWeather | (no native VPD) | mm | ✅ for rain |
| AmbientWeather | hPa | inches | ✅ |
| Weather Underground | hPa | inches | ✅ |
| WeatherFlow Tempest | hPa | mm | ✅ |
| Custom template (kPa, mm) | kPa | mm | ✅ |

If your weather provider uses a unit not in the tables, the
integration logs a warning naming the unit and the entity, and passes
the value through unchanged. Add your unit to `weather.py` via PR
or open an issue.

#### Backward compatibility

- **No breaking changes.** Existing configs continue to work; the
  conversion happens transparently. If your VPD entity already
  reported in kPa (e.g. you set up a template helper as a workaround),
  the new code multiplies by 1.0 and leaves it alone.
- **Calculator output may change** for installs whose VPD or rain
  entities reported in non-target units before. The new value is the
  CORRECT one — the previous value was over- or under-watering. On
  the first install where rc-2 fixes a unit, expect a one-time jump
  in `sensor.z2m_irrigation_today_calculation`.
- The dashboard, JS cards, schedule engine, and all other v4.0
  components are unchanged.

#### Validation

- All Python files byte-compile clean
- The conversion tables are tested in isolation by reading entities
  via the supervisor API and confirming round-trip arithmetic
- Tested live against an Ecowitt GW2000C reporting VPD in hPa: the
  calculator output dropped from 172.8L to ~108L matching the
  hand-computed expected value

## [4.0.0rc1] - 2026-04-08

### 🏁 v4.0 release candidate 1 — final alpha closeout

The last v4.0 alpha. Closes the polish gap between alpha-6 and the
v4.0.0 final tag: in-dashboard schedule editor, queue-runner safety
fix for manual concurrent sessions, dashboard tweaks, and the full
demolition guide for tearing down the legacy v3.x stack.

After rc-1 the v4.0 backend AND frontend are feature-complete. v4.0.0
is a pure version-bump on top of rc-1 once the user has run rc-1 in
production for at least a week with no regressions.

#### What changed

##### New — in-dashboard schedule editor

`custom_components/z2m_irrigation/www/z2m-irrigation-schedule-editor-card.js`
ships alongside the alpha-6 embed card. Self-contained vanilla
custom element, ~470 lines, no framework, no helpers required.
Renders a real form with:

- **Name** text input
- **Time** HTML5 time picker
- **Days** chip selector (mon..sun, empty = every day)
- **Mode** dropdown (smart / fixed)
- **Zones** chip selector, auto-populated from discovered valves
  via `hass.states` scan (entities with a matching `*_zone_factor`
  sensor are integration valves)
- **Fixed liters per zone** number input (only shown when mode = fixed)
- **Enabled** checkbox
- Reset / Submit buttons with disabled state during submission

On submit, calls `hass.callService('z2m_irrigation', 'create_schedule', …)`
with full client-side validation (name required, time must be HH:MM,
fixed mode requires positive liters + ≥ 1 zone). Success and error
feedback are rendered inline. Auto-resets the form on success.

The card is auto-registered as a Lovelace custom element via the
same `_register_frontend_once` helper as the alpha-6 embed card.
Drop into any dashboard with one line of YAML:

```yaml
type: custom:z2m-irrigation-schedule-editor-card
```

The Schedule tab of the v4.0 dashboard now uses this card instead
of the "use Developer Tools" markdown prompt that shipped in alpha-5.

##### Frontend registration refactor

`__init__.py._register_frontend_once` now iterates a
`_FRONTEND_RESOURCES` list of `(filename, label)` tuples instead of
hardcoding the embed card path. Adding a new card is one line in the
list. Both the modern async `StaticPathConfig` API and the older sync
`register_static_path` are tried. Missing files log a warning per
file and continue.

##### Engine fix — sequential safety against manual concurrent sessions

The alpha-2 queue runner published `start_liters` for the next queued
zone immediately on dequeue, without checking whether ANY other valve
was currently running. If the user had manually opened a valve via
its switch entity (or via `start_liters`) just before a schedule
fired, the queue runner would happily open a second valve in
parallel — opening two valves on the same water supply and skewing
both flow measurements.

rc-1 fixes this:

```python
# In schedule_engine._queue_runner, before publishing the next item:
blocked_by = next(
    (other for other in self.mgr.valves.values()
     if other.session_active and other.topic != item.zone),
    None,
)
if blocked_by is not None:
    while blocked_by.session_active:
        if self.mgr.panic.active or not self.mgr.master_enable:
            self._queue.clear()
            break
        await asyncio.sleep(SCHEDULE_QUEUE_POLL_SECONDS)
    if not self._queue:
        break
    await asyncio.sleep(SCHEDULE_INTER_ZONE_GAP_SECONDS)
```

The runner now waits for *any* in-flight session (manual OR previously
queued) to finish before publishing the next zone, with the same
panic + master-enable gate checks applied during the wait. This
preserves the strict-sequential FIFO semantics promised in Stage 2,
even when the user mixes manual and scheduled runs.

##### Dashboard polish

- **Schedule tab** — replaced the "use Developer Tools to create"
  markdown prompt with `type: custom:z2m-irrigation-schedule-editor-card`,
  rendered inline. Schedule creation is now a one-step in-dashboard
  flow with no helpers, no service-call YAML.
- **Today tab** — restructured the per-zone tile auto-entities filter
  to use a top-level `exclude:` clause for the master enable switch
  instead of an inline `not:` clause. Cleaner and more compatible
  with all auto-entities versions.

##### New file — `DEMOLITION.md`

Repo-root teardown guide for v3.x → v4.0 migration. Walks the user
through:

1. **Pre-flight** — verify v4.0 stack is healthy before touching legacy
2. **Backup** — exact `cp` commands for the rollback path
3. **Stage 1: disable, don't delete** — automations / scripts /
   template sensors / input helpers, with the specific entity name
   patterns to look for in each
4. **Stage 2: verify nothing depends on legacy** — Developer Tools
   template snippet to test for orphaned entity refs, log search
   patterns
5. **Stage 3: delete** — file-by-file deletion order (configuration.yaml,
   automations.yaml, scripts.yaml, helper UI, dead Lovelace cards,
   recorder filter cleanup)
6. **What v4.0 absorbed** — full mapping table of legacy thing →
   v4.0 replacement (16 entries covering calculator, per-zone config,
   master enable, skip-today, time-of-day automations, scripts,
   timers, week summary, next run, any-running, panic, charts,
   dashboard, pump notification)
7. **What NOT to touch** — the integration's own JSON store, SQLite
   db, Z2M valve devices, integration entry
8. **Rollback** — exact restore commands
9. **After demolition** — what the user should expect to be left with
10. **Three questions to answer** before demolishing — calculator
    output parity, multi-zone sequencing semantics, kill switch wiring

The guide is the explicit "soft migration" path from Stage 1 design:
v4.0 runs in parallel with the legacy stack until the user has
verified parity, then v3.x gets uninstalled in stages with a 3-day
soak between each.

#### Backward compatibility

- v3.2.1 through v4.0-alpha-6 behavior is preserved end-to-end.
- The new schedule editor card is purely additive — the alpha-6
  embed card and the alpha-5 dashboard remain unchanged in
  functionality. The dashboard tweak is the only user-visible
  delta on the dashboard side.
- The engine fix is a strict tightening: schedules that previously
  ran concurrently with manual sessions will now wait for the
  manual session to complete first. This is the documented Stage 2
  behavior; alpha-2 had a hole that rc-1 closes.
- DEMOLITION.md is documentation only; nothing in it touches the
  integration code.

#### Validation

- All Python files byte-compile clean
- All YAML/JSON parses cleanly
- Both JS files parse via `new Function(src)` without errors
- Total integration: ~7,800 lines (Python + JS + YAML + Markdown)

#### Path to v4.0.0 final

`v4.0.0` is a single-line manifest bump from rc-1 once:

1. rc-1 has been deployed to a real install
2. At least one full week of normal scheduled runs have completed
   without regressions
3. The DEMOLITION guide has been walked through (or explicitly
   deferred — demolition is optional)
4. The kill switch + panic path has been smoke-tested with a real
   trip
5. No GitHub issues have been opened against rc-1 that fall under
   "must fix before final"

When all five are true, bump `manifest.json` from `4.0.0rc1` to
`4.0.0` and tag the release.

## [4.0.0a6] - 2026-04-08

### 🎨 v4.0 alpha 6 — embed card

A standalone custom Lovelace card so any *other* dashboard can drop a
compact "is irrigation happening right now?" indicator with one line
of YAML, regardless of whether the target dashboard has button-card
or mushroom installed.

The card is auto-registered as a frontend resource by the integration,
so the user doesn't need to add a Lovelace resource entry by hand.
Five visual states (panic / running / paused / scheduled / idle) plus
a compact mode toggle.

#### What ships

- **`custom_components/z2m_irrigation/www/z2m-irrigation-embed-card.js`**
  — single self-contained vanilla custom element, ~370 lines, no
  framework, no build step. Renders into a shadow DOM with all styles
  scoped locally so it can't conflict with the host dashboard's CSS.
- **Auto-registration in `__init__.py`** — new `_register_frontend_once`
  helper that:
  1. Resolves the JS path under the integration's package directory
  2. Tries the modern `hass.http.async_register_static_paths` API first;
     falls back to the older sync `register_static_path` for HA < 2024.7
  3. Calls `frontend.add_extra_js_url(hass, …)` so the resource is
     auto-loaded into every dashboard
  4. Tracks a module-level `_FRONTEND_REGISTERED` flag so multiple
     config entries don't double-register
  5. Logs a warning if the JS file is missing or registration fails,
     but doesn't crash setup — the integration still works without
     the embed card.

#### Card config

```yaml
type: custom:z2m-irrigation-embed-card
compact: false                       # default false
title: Irrigation                    # default "Irrigation"
navigation_path: /irrigation/today   # default null (no tap target)
```

#### State resolution

Pure JS function `resolveState(hass)` reads four entities in priority
order and returns one of `panic`, `running`, `paused`, `scheduled`,
or `idle`:

| Priority | Entity | Resolved state |
| --- | --- | --- |
| 1 | `binary_sensor.z2m_irrigation_panic` == on | panic |
| 2 | `binary_sensor.z2m_irrigation_any_running` == on | running |
| 3 | `switch.z2m_irrigation_master_enable` == off | paused |
| 4 | `sensor.z2m_irrigation_next_run_summary` ≠ no_schedule | scheduled |
| 5 | (fallback) | idle |

#### Visual variants

- **Panic** — red left accent, subtle red background tint, reason +
  affected-valves list. The card shows the panic reason from the
  binary sensor's attributes so the user can decide whether to clear.
- **Running** — teal left accent, valve friendly name as the title,
  live `liters / target L · flow_lpm L/min` sub-line, animated progress
  bar (transitions over 400ms ease as the value updates), elapsed +
  ETA in the bottom row. Pure CSS — no chart library. The progress bar
  is hidden if the run is timed (no target_liters).
- **Paused** — grey left accent, "Master Enable to resume" hint.
- **Scheduled** — teal left accent, formatted next-run weekday + time
  as the title, schedule name + zone count + estimated total liters
  in the sub-line. Skip-today flag prepends a "⏭ skipped today" chip.
- **Idle** — grey left accent, "No schedule yet" hint.

#### Compact mode

Collapses padding (`14px 18px` vs `20px 22px`), drops the accent label,
shrinks title font (`15px` vs `22px`), thins the progress bar (`4px` vs
`6px`), and hides the elapsed/ETA secondary row. Designed to fit in a
sidebar column or alongside other compact cards.

#### Re-render guard

The card reads from `hass` on every state push but only re-runs the
DOM update when its own fingerprint changes (state + compact + active
session liters/flow + next-run + panic). Saves a few cycles on
dashboards that re-push hass on every state event for unrelated
entities.

#### Tap-to-navigate

If `navigation_path` is set in the card config, the card is rendered
as clickable (cursor + hover transform) and tap fires the standard
Lovelace `location-changed` event so the host dashboard's router picks
it up. Default is no tap action — the card is purely informational
unless a path is explicitly configured.

#### Anti-XSS

All entity-derived strings flow through a local `_escape` helper that
HTML-escapes `<`, `>`, `&`, `"`, `'`. Defends against a hypothetical
attribute that contains markup (e.g. a malicious schedule name).

#### Logging

The card logs a single `console.info` line on registration with its
version (`4.0.0a6`) so users can confirm the right copy is loaded
when troubleshooting. Visible in the browser devtools console as a
teal pill.

#### Dependencies

**None.** The card is vanilla JS with a shadow DOM. The host dashboard
does not need any of the card libraries (button-card / mushroom /
auto-entities) that the full Lovelace dashboard from alpha-5 uses.
This is the whole point of the embed card — drop it anywhere with no
prerequisites beyond the integration itself being loaded.

#### Backward compatibility

- v3.2.1 through v4.0-alpha-5 behavior is preserved end-to-end.
- The new frontend registration is opt-out via missing-file detection:
  if the JS isn't there for any reason, setup logs a warning and
  continues. Existing entities and services are unaffected.
- The static path is registered globally (not per-config-entry) so
  re-setup of the integration doesn't break the resource.
- The embed card uses entity IDs that have been stable since alpha-1,
  so it works against any v4.0 alpha or later install.

#### What's still pending in v4.0

- **rc-1** — polish, in-dashboard schedule editor (replacing the
  current "use Developer Tools" prompt), demolition guide for
  legacy v3.x helpers and template sensors, edge cases.

## [4.0.0a5] - 2026-04-08

### 🎨 v4.0 alpha 5 — pre-built Lovelace dashboard

The user-visible heart of v4.0. After four backend alphas (storage,
calculator, scheduler, history, aggregation), alpha-5 ships the
single-file dashboard YAML that wires every entity into the editorial
4-tab UI we designed in Stage 1.

No changes to the integration code itself in alpha-5 — just a manifest
version bump so the dashboard ships in the same release. Anyone
deploying alpha-5 picks up the dashboard alongside whatever entity
contract was finalised in alpha-4.

#### What ships

- **`dashboards/z2m_irrigation.yaml`** — single self-contained dashboard
  YAML, ~600 lines. Defines:
  - 3 shared `button-card` templates: `z2m_base` (typography +
    palette), `z2m_hero` (5-state hero card), `z2m_zone_tile` (per-zone
    tile on the Today tab)
  - 4 views (`type: sections`, `max_columns: 2`):
    1. **Today** — Hero status, calculator card (markdown editorial
       prose with per-zone breakdown), per-zone live tiles via
       auto-entities, manual run sliders
    2. **Schedule** — next-run summary, queue snapshot, all-schedules
       list with per-row tap=run-now / hold=enable-disable, links to
       create/update/delete services
    3. **Setup** — master enable / panic clear / rescan / recalculate
       chips, per-zone in_smart_cycle toggles, integration option
       links
    4. **Insight** — combined 30-day stacked-bar chart via
       apexcharts-card, per-zone leaderboard table, per-zone
       trend charts (one bar chart per discovered valve via
       auto-entities), schedule timeline (last 30 events from
       `schedule_history`), avg flow per zone glance strip
- **`dashboards/README.md`** — install instructions, dependency list,
  first-time check, customization notes, troubleshooting table.

#### Hero card — 5 states

The Hero card resolves its state by reading 4 entities in this priority
order:
1. `binary_sensor.z2m_irrigation_panic` → "🚨 Kill the water pump"
2. `binary_sensor.z2m_irrigation_any_running` → "Running …" + live
   liters / target / flow / ETA from `active_session_summary`
3. `switch.z2m_irrigation_master_enable` off → "Paused"
4. `sensor.z2m_irrigation_next_run_summary` state == `no_schedule` → "No schedule yet"
5. otherwise → "Next run …" with formatted weekday/time + zone count
   and estimated total liters

The 5 states are visually distinguished by an accent stripe on the
left edge of the card and (in panic state) a subtle background tint.
The state logic lives in `button_card_templates.z2m_hero.custom_fields`
and is pure JS — no template helpers needed.

#### Calculator card

Markdown card that reads `sensor.z2m_irrigation_today_calculation`
attributes and renders an editorial-style prose block:

> **{total} L** total across **{runnable}** of **{total_zones}** zones.
>
> VPD **X kPa** · rain today **Y mm** · forecast 24h **Z mm** ·
> dryness factor **D**
>
> ---
>
> **{zone}** — {liters} L ({need_mm} mm × {l_per_mm} L/mm × {factor})
> ~~**{zone}** — skipped (below_min_run)~~

Each zone shows the full formula breakdown so the user can see why a
zone got the volume it did. Skipped zones are struck through with
their skip reason.

#### Per-zone tiles + auto-entities

Today tab uses `auto-entities` filtered to
`integration: z2m_irrigation` and `domain: switch` (excluding the
master enable switch). Each match renders as a `button-card` instance
templated with `z2m_zone_tile`, which reads:
- `entity.attributes.friendly_name` for the title
- `entity.state` for open/closed status
- `sensor.<base>_last_run_liters.state` for the metric
- `sensor.<base>_last_run_at.state` for the subtitle (formatted)

The pattern auto-extends to any future valve discovered post-deploy
without dashboard edits.

#### Schedule list

Built from a Jinja template that iterates
`state_attr('sensor.z2m_irrigation_schedules', 'schedules')` and emits
a `mushroom-template-card` per schedule. Per-row interactions:
- **Tap** → call `run_schedule_now` (force-fire, gates still apply,
  with confirmation)
- **Hold** → call `enable_schedule` / `disable_schedule` (toggles)
- **Title** → schedule name + "(disabled)" suffix when applicable
- **Subtitle** → time, days, mode, zone count, last outcome

A "Cancel queued runs" chip at the bottom calls `cancel_queue` for
panic-stopping a multi-zone run mid-flight (in-flight session is left
to existing failsafes; the chip just drops the rest of the queue).

#### Insight charts

The 30-day combined chart uses `apexcharts-card` with a
`data_generator` that pulls from
`sensor.z2m_irrigation_daily_totals.attributes.days[]` — no recorder
queries, no statistics graph, just the alpha-4 cache rendered as bars.

The per-zone trend section uses `auto-entities` to enumerate every
`sensor.*_daily_history` and emit one `apexcharts-card` per zone, each
reading from its own `attributes.days[]`. This gives one bar chart per
discovered valve with no per-valve YAML.

#### Dependencies

8 HACS frontend cards listed in the README:
`button-card`, `mushroom`, `auto-entities`, `apexcharts-card`,
`mini-graph-card`, `stack-in-card`, `card-mod`, `layout-card`. The user
already has all 8 installed per the v4.0 design conversation, but the
README lists them so anyone else picking this up knows what to install
first.

#### Customization

The dashboard uses 3 button-card templates at the top so re-theming is
a single search-replace. The accent color is `#0d7377` (teal); the
font stack is the system Apple-style stack
(`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue"`).
README has a "Customization" section with the exact knobs to tweak.

#### What's still pending in v4.0

- **alpha-6** — JS embed card (`<z2m-irrigation-embed-card>`). A small
  custom element that registers as a Lovelace card so the user can
  drop a compact running-indicator into any other dashboard with one
  line of YAML, regardless of whether `button-card` is installed
  there. Three variants: idle / running / panic.
- **rc-1** — polish, in-dashboard schedule editor (replacing the
  current "use Developer Tools" prompt), demolition guide for legacy
  v3.x helpers, edge cases.

## [4.0.0a4] - 2026-04-08

### 📊 v4.0 alpha 4 — daily aggregation cache + chart-ready sensors

The data layer for the dashboard's Insight tab. Pre-builds per-day
per-zone delivery summaries from the existing SQLite session history,
caches them on the manager, and persists a snapshot to the JSON store
so cold-restart hydration is instant. Two new sensors expose the
aggregation as ready-to-render attributes for the alpha-5 dashboard.

This is the last data-layer alpha. After alpha-4, the integration's
backend is feature-complete for v4.0; alpha-5 onwards is pure UI work
(dashboard YAML, embed card, polish).

#### New module — `aggregator.py`

Pure data-shaping module. The dashboard cards re-render frequently and
running a SQLite group-by over 30 days × N valves on every render would
be wasteful, so we build the cache once on a schedule and read from it
on every render.

- **`DayBucket`** — one day of delivery: `{date, liters, minutes, sessions}`.
- **`ZoneSeries`** — time-series of `DayBucket`s for one zone, with
  total properties (`total_liters`, `total_minutes`, `total_sessions`).
- **`DailySummary`** — full snapshot: `days_back`, `built_at`, list of
  `ZoneSeries`, and a combined-across-zones `List[DayBucket]`.
  Round-trippable to/from JSON via `to_dict` / `from_dict` for the
  ZoneStore persistence path.
- **`zero_fill(rows, days_back)`** — sparse → dense converter. The SQL
  query only returns days that had at least one session; the dashboard
  chart wants every date in the window so the bars line up. Always
  produces exactly `days_back` entries, most-recent first.
- **`sum_by_date(zone_series)`** — combine per-zone series into a
  single across-all-zones series. Used to build the
  `DailySummary.combined` list.
- **`build_daily_summary(db, valves, *, days_back=30)`** — async
  orchestrator. Queries the SQLite db once per valve, zero-fills, and
  combines. Pure data — passes `valves` as a generic dict to avoid
  importing the `Valve` dataclass and creating a circular import.

#### New SQL — `IrrigationDatabase.get_daily_breakdown`

```sql
SELECT
    DATE(ended_at) AS day,
    COALESCE(SUM(volume_liters), 0) AS liters,
    COALESCE(SUM(duration_minutes), 0) AS minutes,
    COUNT(*) AS sessions
FROM sessions
WHERE valve_topic = ?
  AND ended_at IS NOT NULL
  AND ended_at >= ?
GROUP BY DATE(ended_at)
ORDER BY day DESC
```

Buckets on `ended_at` rather than `started_at` so a session that spans
midnight is attributed to the day it finished — matches how a user
typically thinks about "what watered today". Cheap (uses the existing
`idx_sessions_ended` index from v3.x).

#### Manager wiring

- **New attribute `manager.daily_summary: Optional[DailySummary]`** —
  the in-memory cache. Hydrated from the persisted ZoneStore snapshot
  on `async_start()`, then refreshed in three places:
  1. `_periodic_refresh_time_metrics` — every 15 minutes alongside
     the existing 24h/7d aggregation refresh and the calculator
     refresh. The Today and Insight tabs stay in lockstep.
  2. `_ensure_valve` — refreshed once on first valve discovery so the
     dashboard has data immediately rather than waiting up to 15 min
     for the next periodic tick.
  3. The session-end `_end_and_sync` path — after a session is
     committed to the SQLite db, the aggregation is rebuilt so the
     just-completed run shows up on the chart immediately.
- **`manager.refresh_daily_summary()`** — public coroutine; safe to
  call any time. Returns the new `DailySummary` (or None if there are
  no valves yet, in which case the existing cache is preserved
  untouched). Persists a snapshot via `zone_store.set_daily_summary`
  on every successful build, then fires `_notify_global()` so the
  dependent sensors refresh.
- **Cold-start hydration** — `async_start` reads the persisted snapshot
  via `zone_store.get_daily_summary()` and inflates it via
  `DailySummary.from_dict`. The dashboard chart has data immediately
  on HA restart even before any valves have been re-discovered or any
  refresh has run.

#### ZoneStore additions

- **New top-level slot `daily_summary`** — holds the `DailySummary.to_dict()`
  output. None until the first refresh. Tolerates legacy stores that
  don't have the key.
- **`zone_store.get_daily_summary()`** — sync read of the persisted snapshot.
- **`zone_store.set_daily_summary(snapshot)`** — async write + persist.

#### New entities

- **`sensor.z2m_irrigation_daily_totals`** — global. State = total
  liters across all zones over the cached window (default 30 days).
  Attributes carry:
  - `days_back`, `built_at`
  - `total_liters`, `total_minutes`, `total_sessions`
  - `days[]` — combined per-day series (for the stacked-bar chart)
  - `zones[]` — per-zone totals over the same window (for the
    "top-watered zones" leaderboard)
- **`sensor.<zone>_daily_history`** — per-valve. Appears under each
  existing valve device card alongside the alpha-3 history sensors.
  State = total liters delivered by this zone over the cached window.
  Attributes carry the per-day series with zero-filled gaps so the
  per-zone chart bars line up. Subscribes to BOTH the per-valve update
  channel and the global update channel so service-driven aggregation
  refreshes propagate without waiting for an MQTT message.

#### Performance notes

- The cache is small: ~30 days × ~10 zones × ~50 bytes ≈ 15 KB. Well
  within HA's recommended attribute size limit, even when the dashboard
  reads the full attribute set on every render.
- Refresh cost: one SQL query per valve, ~ms each on a typical pi-class
  HA installation. Total refresh time on a 10-zone install: well under
  100ms. The 15-min periodic loop is the dominant cadence; per-session
  refreshes are infrequent enough to not matter.
- The persisted snapshot adds ~15 KB to the JSON store on disk; well
  within HA's `Store` helper's tolerances.
- No new SQLite indexes needed — the existing `idx_sessions_ended`
  already covers the `WHERE ended_at >= ?` lookup.

#### Backward compatibility

- v3.2.1 through v4.0-alpha-3 behavior is preserved end-to-end.
- The new sensors are additive — none replace any existing entity.
- The new ZoneStore key `daily_summary` is tolerated as missing on
  load (legacy stores hydrate to `None` and the first refresh
  populates it).
- The new SQLite method `get_daily_breakdown` does not modify the
  schema or any existing data — pure read.
- Cold start with an empty store: the new sensors report `unknown`
  until the first valve is discovered AND the first refresh has run
  (typically within seconds of HA finishing startup).

#### What's still pending in v4.0

- **alpha-5** — pre-built storage-mode Lovelace dashboard YAML
  (4 tabs: Today / Schedule / Setup / Insight) shipped in
  `dashboards/z2m_irrigation.yaml`. Reads all the data the alpha-1
  through alpha-4 entities expose; no integration-side changes needed
  for alpha-5 to work.
- **alpha-6** — JS embed card (`<z2m-irrigation-embed-card>`).
- **rc-1** — polish, demolition guide for legacy helpers, edge cases.

## [4.0.0a3] - 2026-04-08

### 📜 v4.0 alpha 3 — history persistence & per-zone history sensors

The third alpha. With the scheduler engine landed in alpha-2, alpha-3
adds the persistent history layer and the per-zone history-derived
sensors that the dashboard's Insight tab will read in alpha-5. Existing
v3.x and earlier-alpha behavior is preserved.

#### What changed

- **Schedule timeline persistence** — every time a schedule fires or
  skips, the engine now appends a record to a new global timeline kept
  in the JSON ZoneStore under the `_schedule_events` namespace. Records
  are pruned on every write: anything older than 90 days
  (`HISTORY_RETENTION_DAYS`) is dropped, and any namespace with more
  than 500 records (`HISTORY_MAX_ENTRIES`) is truncated to the most
  recent 500. Both bounds are constants in `const.py`.
- **`ZoneStore.record_schedule_event`** — new method called by both
  `_fire_schedule` (kind=`fired`) and `_record_skip` (kind=`skipped`).
  Records carry: `at`, `kind`, `schedule_id`, `schedule_name`,
  `outcome`, `mode`, `trigger`, `zones`, `total_liters`. The trigger
  field distinguishes `scheduled` (per-minute tick), `catchup` (startup
  catch-up), and `manual` (`run_schedule_now` / `run_smart_now`).
- **`ZoneStore.schedule_events(limit=N)`** — most-recent-first read API
  used by the new global sensor.
- **`ZoneStore.reset_zone_to_defaults`** — back-end for the new
  `reset_zone_to_defaults` service.

#### New entities

- **`sensor.z2m_irrigation_schedule_history`** — global timeline.
  State = total recorded events in the retention window. The `events`
  attribute carries the most recent 100 (clamped to keep the recorder
  happy). Each event includes timestamp, kind, outcome, schedule, mode,
  trigger, zones, and total_liters. Powers the Insight tab's "what
  happened in the last 7 days" timeline.
- **Per-zone (per-valve) history sensors** — appear under each existing
  valve device card alongside the v4.0-alpha-1 zone config sensors:
  - `sensor.<zone>_avg_flow_7d` (L/min) — rolling average flow rate
    over the most recent 5 completed sessions for this valve. Refreshed
    by the manager's existing 15-min `_periodic_refresh_time_metrics`
    loop AND on every session end. Reports `unknown` until at least
    one completed session exists. Used by the Insight tab to spot a
    degrading flow rate (clogged filter, valve wear, pressure drop)
    and by the ETA computation in the active session sensor.
  - `sensor.<zone>_last_run_liters` (L) — volume delivered in the most
    recent completed session. Distinct from "Last 24h" / "Last 7 Days"
    (windowed sums) — this is the single-event delivery the dashboard
    per-zone tile shows under "last run: X L".
  - `sensor.<zone>_last_run_at` (timestamp) — wall-clock end of the
    most recent session. Mirrors v3.x's `Last Session End` with the
    new dashboard-friendly name.
- **Per-zone `binary_sensor.<zone>_in_smart_cycle`** — `on` when the
  zone is enrolled in the smart-watering cycle. Stage 2 promised this
  in alpha-1 but it was missed; landing now. Subscribes to BOTH the
  per-valve update channel and the zone-config-changed channel so
  service-driven edits flip the state instantly.

#### Manager — new `Valve` fields

- `Valve.avg_flow_lpm_7d: Optional[float]` — rolling avg flow over the
  last `HISTORICAL_FLOW_LOOKBACK_SESSIONS` completed sessions. Refreshed
  in 3 places: initial `_ensure_valve` load, the existing 15-min
  periodic loop, and the session-end `_end_and_sync` path. Reads from
  the existing SQLite `db.get_recent_avg_flow` — no schema changes to
  the SQLite store.
- `Valve.last_session_liters: Optional[float]` — volume delivered in
  the most recent completed session. Stamped by `_end_and_sync`
  immediately after the existing totals sync, so the new
  `last_run_liters` sensor updates without an extra DB read.

#### New service

- **`z2m_irrigation.reset_zone_to_defaults`** — replace one zone's
  stored config (factor, l_per_mm, base_mm, in_smart_cycle, skip
  threshold overrides, display fields) with the integration defaults.
  Does NOT touch the zone's session-history rows in the SQLite database
  — those are the long-term record and are never wiped by a config
  edit. Fires `zone_config_changed::<zone>` and triggers a fresh
  calculator run.

#### New constants

- `HISTORY_MAX_ENTRIES = 500` — hard cap per history namespace.
- `AVG_FLOW_LOOKBACK_DAYS = 7` (informational; the SQLite query uses
  the existing `HISTORICAL_FLOW_LOOKBACK_SESSIONS = 5` constant).
- `AVG_FLOW_LOOKBACK_SESSIONS = 10` (informational; reserved for an
  alpha-4 dashboard chart that wants a longer window than the
  guardrail Layer 4 uses).

#### Backward compatibility

- v3.2.1, v4.0-alpha-1, and v4.0-alpha-2 behavior is preserved
  end-to-end. New entities are additive — none replace or shadow
  existing v3.x sensors. The session-history SQLite database is
  unchanged; new fields on the `Valve` dataclass are populated from
  existing DB queries.
- The schedule timeline is **not** retroactive — events that happened
  before deploying alpha-3 are not in the timeline (the SQLite session
  history still has the per-session data). The timeline starts
  recording fires/skips from the moment alpha-3 is deployed.
- The two new alpha-1 placeholder sensors that became real in alpha-2
  (`next_run_summary`, `schedules`) are unchanged. The new
  `schedule_history` sensor is additive.
- `reset_zone_to_defaults` is the only new "destructive" operation in
  alpha-3, but it only touches the JSON config store, not the SQLite
  session history. Re-creating the zone defaults is an idempotent
  operation that the user can run any time without losing measurement
  data.

#### What's still pending in v4.0

- **alpha-4** — per-zone session-summary records in the JSON store
  (separate from the SQLite db, optimized for fast dashboard reads),
  with chart-ready aggregations.
- **alpha-5** — pre-built storage-mode Lovelace dashboard YAML
  (4 tabs: Today / Schedule / Setup / Insight).
- **alpha-6** — JS embed card.
- **rc-1** — polish, demolition guide for legacy helpers, edge cases.

## [4.0.0a2] - 2026-04-08

### ⏰ v4.0 alpha 2 — scheduler engine

The scheduler engine. Schedules now actually fire, with calculator-driven
zone selection in smart mode and explicit per-zone amounts in fixed mode.
Sequential FIFO run queue, panic-aware gating, restart catch-up, and full
schedule CRUD via service calls. Two new placeholder sensors from
alpha-1 (`next_run_summary`, `schedules`) are now backed by real engine
state.

Existing v3.x and v4.0-alpha-1 behavior is preserved. The engine plugs
into the manager's existing `start_liters` for each queue item, so all
guardrails, panic logic, kill switch, and per-valve sensors continue to
work unchanged whether a session was started by the engine or a manual
call.

#### New module — `schedule_engine.py`

`ScheduleEngine` is the heart of alpha-2. Owned by `ValveManager`,
shares its lifecycle (`start()` / `stop()`).

- **Per-minute tick** — `async_track_time_change(second=0)` examines all
  enabled schedules each minute and fires any whose `time` matches the
  current local-time HH:MM and whose `days` filter matches today's
  weekday. The engine tracks `_fired_today` to prevent double-fires
  within the same minute window; the set auto-clears at local-midnight.
- **Sequential run queue** — a single FIFO `deque[QueueItem]`. Multi-zone
  schedules enqueue all their resolved zones at once. The queue runner
  is a single asyncio task that publishes one valve, waits up to 60s for
  the device to ack ON, polls `valve.session_active` until it flips OFF,
  then advances after a 5-second inter-zone gap. The runner rechecks
  panic + master_enable between every zone — a panic during a multi-zone
  schedule drops all remaining queue entries (the in-progress session is
  left to existing failsafes / kill switch).
- **Pre-fire gates** (in order):
  1. `master_enable` — paused integrations skip with outcome
     `skipped_master_paused`.
  2. `panic.active` — outcome `skipped_panic`.
  3. `skip_today` flag (in-memory, auto-clears at midnight) — outcome
     `skipped_today`.
  4. **Smart mode only**: rain today and rain forecast 24h thresholds
     from the integration options — outcomes `skipped_rain` /
     `skipped_forecast`. Fixed mode bypasses these (the user explicitly
     asked for N liters; we don't second-guess them with weather).
  5. Zone resolution + filtering — outcome `skipped_no_zones` if nothing
     to run after applying smart-cycle membership and per-zone min-run
     thresholds.
- **Restart catch-up** — on engine start, after a brief 5-second delay
  (so valves are discovered first), the engine looks at every enabled
  schedule whose fire-time was earlier today and the schedule has not
  already run today. If the miss is within 30 minutes (the
  `SCHEDULE_CATCHUP_WINDOW_MINUTES` constant), the schedule fires
  immediately. Outside that window the miss is recorded as
  `skipped_catchup_window` and the user can manually re-trigger via
  `run_schedule_now`. The catch-up window is the design choice from
  Stage 2: short enough to avoid surprise watering hours after the
  intended time, long enough to cover a typical post-update HA restart.
- **No queue persistence across HA restart** — Stage 2 explicitly chose
  abandon-on-restart for safety. Schedule `last_run_at` is stamped as
  soon as the engine commits to firing (before the queue runner
  actually starts), so a restart mid-run does NOT cause the catch-up
  loop to re-fire the same schedule.
- **Bus events**:
  - `z2m_irrigation_schedule_fired` — schedule passed all gates and was
    enqueued. Carries `schedule_id`, `schedule_name`, `mode`, `trigger`
    (`scheduled` / `catchup` / `manual`), `zones`, `total_liters`.
  - `z2m_irrigation_schedule_skipped` — gate failed. Carries the
    outcome label so external automations can route notifications.
  - `z2m_irrigation_smart_run_started` — `run_smart_now` service was
    called and produced at least one queue item.

#### New module — `zone_store.py` schedule CRUD

The `Schedule` dataclass and `create_schedule` / `update_schedule` /
`delete_schedule` / `mark_schedule_run` methods. Schedule ids are short
opaque tokens (`sch_<16-hex>`) generated via `secrets.token_hex(8)` —
no external dependency. The CRUD methods persist immediately via the
existing HA `Store` helper. `all_schedules_typed()` returns the typed
view used by the engine; `all_schedules()` returns the raw dict list
used by the dashboard sensor.

#### Schedule data model

```jsonc
{
  "id": "sch_a1b2c3d4e5f60718",
  "name": "Morning smart",
  "enabled": true,
  "time": "06:00",                 // HH:MM, local timezone
  "days": ["mon", "wed", "fri"],   // [] = every day
  "mode": "smart",                  // "smart" | "fixed"
  "zones": ["front_garden", "lilly_pilly"],   // [] in smart = all in_smart_cycle
  "fixed_liters_per_zone": null,    // only used when mode = "fixed"
  "created_at": "2026-04-08T...",
  "last_run_at": null,
  "last_run_outcome": null          // ran | skipped_rain | ... | error
}
```

#### New services

- `z2m_irrigation.create_schedule` — create a new schedule. Required
  fields: `name`, `time`. Optional: `days`, `mode`, `zones`,
  `fixed_liters_per_zone`, `enabled`.
- `z2m_irrigation.update_schedule` — patch-update by `schedule_id`.
- `z2m_irrigation.delete_schedule` — permanently remove a schedule.
- `z2m_irrigation.enable_schedule` / `disable_schedule` — toggle the
  enabled flag without losing the rest of the schedule config.
- `z2m_irrigation.run_schedule_now` — force-fire a specific schedule
  immediately, ignoring its time/day filter. Safety gates still apply.
- `z2m_irrigation.run_smart_now` — ad-hoc smart cycle. Optional
  `zones` list to limit which zones run; omit for "all in_smart_cycle".
  Same gates as a scheduled smart fire EXCEPT skip-today is bypassed
  (the user explicitly asked).
- `z2m_irrigation.skip_today` / `clear_skip_today` — set/clear the
  in-memory skip-today flag. Auto-clears at next local midnight.
- `z2m_irrigation.cancel_queue` — empty the engine's run queue. The
  in-flight session is NOT cancelled; call `homeassistant.turn_off` on
  the relevant valve switch separately for that.

The dead schedule service stubs that were removed in alpha-1 are now
replaced with these real implementations. The names match Stage 2 spec.

#### New behavior on existing entities

- **`sensor.z2m_irrigation_next_run_summary`** — was a placeholder
  reporting `no_schedule` in alpha-1. Now reports the ISO timestamp of
  the soonest enabled schedule's next firing across all schedules,
  computed by `ScheduleEngine.compute_next_run_summary()` (looks 8 days
  ahead, handles weekday filters). Attributes carry: `next_run_at`,
  `schedule_id`, `schedule_name`, `mode`, `zones`, `estimated_total_liters`
  (smart mode pulls from the calculator cache; fixed mode multiplies),
  plus live `skip_today`, `master_enable`, `panic_active`, and a
  `queue` snapshot of currently-pending zone runs.
- **`sensor.z2m_irrigation_schedules`** — was a placeholder reporting
  count `0` in alpha-1. Now reports the count of *enabled* schedules
  (not total) and the attribute `schedules` carries the full schedule
  list including `last_run_at` and `last_run_outcome` for the dashboard
  Schedule tab to render.

#### Lifecycle

- The engine is created in `ValveManager.__init__` only when a
  `zone_store` was passed (which alpha-1 always does). Started in
  `async_start()` after the calculator refresh loop is set up; stopped
  in `async_stop()`.
- The catch-up phase is deferred 5 seconds after `start()` so the
  manager has time to discover valves first.
- All `_notify_global()` calls fire SIG_GLOBAL_UPDATE which the new
  sensors subscribe to.

#### Backward compatibility

- v3.2.1 and v4.0-alpha-1 behaviour is preserved end-to-end. The engine
  is purely additive: it calls the existing `start_liters` /
  `start_timed` methods, reads `valve.session_active` to know when each
  zone is done, and otherwise touches no manager state.
- Manual `start_liters` / `start_timed` calls bypass the engine entirely
  — the valve runs, the session is logged in the SQLite db as before,
  and the engine's queue is unaffected.
- The new schedule services share names with the dead v3.x stubs that
  were removed in alpha-1, but their schemas match Stage 2 spec, not the
  old (Supabase-shaped) ones. Anyone calling them with the old payloads
  will get a clear voluptuous validation error instead of a silent
  no-op.

#### What's still pending in v4.0

- **alpha-3** — fine-grained per-zone scheduling config; UI conveniences.
- **alpha-4** — per-zone run history persistence; dashboard charts.
- **alpha-5** — pre-built storage-mode Lovelace dashboard YAML.
- **alpha-6** — JS embed card.
- **rc-1** — polish, demolition guide for legacy helpers, edge cases.

## [4.0.0a1] - 2026-04-08

### 🏗️ v4.0 alpha 1 — foundation + surface

v4.0-alpha-1 lays the entire foundation for v4.0 *without* breaking any
v3.2.1 behaviour. The scheduler engine, pre-built dashboard, and embed
card are still pending (alpha-2..rc-1), but every back-end piece those
features need is now in place: per-zone config storage, calculator port,
weather adapter, kill-switch wiring, and a full set of new entities and
services. Existing v3.2.1 valves, sensors, and panic system are
preserved unchanged.

This release is delivered in two commits:
  * **Commit A — foundation** (back-end only, behavioral no-op)
  * **Commit B — surface** (config flow, new entities, new services)

#### What changed in Commit A

- **New JSON config store** (`zone_store.py`) — backed by HA's
  `homeassistant.helpers.storage.Store`, persisted at
  `.storage/z2m_irrigation.<entry_id>`. Stores per-zone calculator config
  (`factor`, `l_per_mm`, `base_mm`, `in_smart_cycle`, per-zone skip
  threshold overrides, display fields). Reserved keys for `schedules` and
  `history` are present but unused in alpha-1; alpha-2 will populate
  schedules, alpha-4 will populate history.
- **New calculator module** (`calculator.py`) — pure-Python port of the
  existing template-helper VPD formula, lifted verbatim so v4.0 produces
  identical numbers to the legacy stack while it runs in parallel.
  Formula: `dryness = clamp(0.85 + vpd/3, 0.8, 1.5)`,
  `need_mm = max(0, base_mm × dryness − rain_today − 0.7 × fc24)`,
  `liters = need_mm × factor × l_per_mm`. Handles missing weather inputs
  gracefully via neutral defaults.
- **New weather adapter** (`weather.py`) — small read-only helper that
  snapshots the user-configured weather entities and produces a
  `WeatherInputs` struct for the calculator. The integration still ships
  with no built-in weather provider; the user wires whatever they have.
- **Per-zone defaults seeded on first sight** — `_ensure_valve` now calls
  `zone_store.ensure_zone(topic)` so every newly-discovered Sonoff SWV
  gets a default config row immediately. Defaults: `factor=1.0`,
  `l_per_mm=12.0`, `base_mm=4.0`, `in_smart_cycle=true`. Existing
  installations pick up defaults on next HA restart with no migration step.
- **Kill switch wiring** — the manager now accepts `kill_switch_entity`
  and `kill_switch_mode` from the config flow, and the panic flow
  (`_trigger_panic`) calls `homeassistant.turn_off` on the configured
  entity as its last line of defense. The existing
  `EVENT_PANIC_REQUIRED` HA bus event still fires in parallel, so any
  external automations layered on top continue to work. Modes:
  `off_only`, `off_and_notify` (default — also creates a critical
  persistent notification), `disabled`. The kill switch is invoked
  best-effort; failure logs a warning but does not crash the panic flow.
- **New per-zone config services**:
  - `z2m_irrigation.set_zone_factor`
  - `z2m_irrigation.set_zone_l_per_mm`
  - `z2m_irrigation.set_zone_base_mm`
  - `z2m_irrigation.set_zone_in_smart_cycle`
  - `z2m_irrigation.set_zone_skip_thresholds` (rain_mm / forecast_mm /
    min_run_liters; pass `null` to clear back to global)
  These are the back-end the v4.0 Setup tab will call. They mutate the
  ZoneStore and dispatch a `z2m_irrigation_zone_config_changed::<zone>`
  signal so the per-zone config sensors (added in Commit B) refresh.
- **Removed dead `scheduler.py`** — that file was a leftover from an
  abandoned Supabase-cloud-backed era. It imported from a non-existent
  `.history` module and was never instantiated by `__init__.py`. The
  schedule CRUD service stubs that logged "disabled in v3.0.0" are also
  removed from `__init__.py`. Alpha-2 will reintroduce the real engine
  and these services backed by it.
- **Manifest bumped to 4.0.0a1**.

#### What changed in Commit B

- **Config flow rewritten as 3 steps in the options flow** —
  initial setup is a single trivial click; all real configuration lives
  in Configure (which can be revisited any time):
  1. **MQTT** — base topic, manual valve names, flow scale (existing v3.x).
  2. **Weather sources** — VPD, rain-today, rain-forecast-24h, temperature
     entity ids. All four are optional `EntitySelector` pickers; the
     calculator falls back to neutral defaults for any that are missing
     or unavailable.
  3. **Safety & global thresholds** — kill switch entity (`switch.*` /
     `input_boolean.*` selector), kill switch mode (off_only /
     off_and_notify / disabled), global skip thresholds (rain mm,
     forecast mm, min run liters).
  Edits in any step are picked up live by the running manager via the
  options-update listener — no HA restart required.
- **`strings.json`** updated with labels for all 3 new steps and every
  new field.
- **New global integration-level sensors** (one of each per config entry):
  - `sensor.z2m_irrigation_today_calculation` — total liters the
    calculator says should be applied today, with full per-zone
    breakdown and weather inputs in the attributes (powers the
    Calculator card on the v4.0 dashboard).
  - `sensor.z2m_irrigation_active_session_summary` — live mirror of the
    currently-running valve (state = friendly name or `idle`), with
    elapsed seconds, ETA, target, flow rate, and shutoff state in the
    attributes (powers the Hero card's Running state).
  - `sensor.z2m_irrigation_week_summary` — total liters delivered across
    all valves in the last 7 days, with per-valve breakdown (powers the
    Insight tab).
  - `sensor.z2m_irrigation_next_run_summary` — placeholder for alpha-1
    (state = `no_schedule`); will be populated by the alpha-2 scheduler.
  - `sensor.z2m_irrigation_schedules` — placeholder for alpha-1
    (state = 0); will be populated by the alpha-2 scheduler.
- **New per-zone (per-valve) config sensors** — appear under each
  existing valve device card:
  - `sensor.<zone>_zone_factor`
  - `sensor.<zone>_zone_l_per_mm`
  - `sensor.<zone>_zone_base_mm`
  Each subscribes both to the per-valve `sig_update` channel (so they
  refresh on any valve state change) and to the new
  `zone_config_changed::<zone>` channel (so they refresh instantly when
  the user calls one of the `set_zone_*` services).
- **New `switch.z2m_irrigation_master_enable`** — global pause flag,
  backed by `RestoreEntity` so a paused integration stays paused after
  HA restart. Toggling fires `SIG_GLOBAL_UPDATE`. Pause only affects
  scheduled runs (which the alpha-2 scheduler will consult); manual
  `start_liters` / `start_timed` calls and in-flight sessions are NOT
  affected by this flag.
- **New `binary_sensor.z2m_irrigation_any_running`** — `on` when any
  valve has an active session, `off` otherwise. Subscribes to per-valve
  `sig_update` for every existing and future valve. Powers the embed
  card's compact running indicator and is the recommended single-boolean
  trigger for "irrigation is currently happening" automations.
- **New service `recalculate_now`** — force an immediate calculator
  refresh without waiting for the 15-min periodic loop. Auto-called
  whenever any of the `set_zone_*` services run, so users typically
  don't need to call it themselves.
- **`services.yaml` rewritten** — removed the dead schedule CRUD entries
  (they were stubs in v3.x), added detailed entries with selector hints
  for all 5 `set_zone_*` services and `recalculate_now`. The existing
  `start_timed`, `start_liters`, `reset_totals`, `rescan`, `clear_panic`
  entries were rewritten in the new selector style.
- **Calculator wiring** — `__init__.py` reads the new weather + global
  threshold options from the config flow and pushes them onto
  `ValveManager` attributes. The manager runs `recalculate_today()` on a
  15-min interval, on first valve discovery, on every zone config edit,
  and on options-flow updates, so the `today_calculation` sensor is
  always fresh.
- **Master enable hook** — `set_master_enable()` on the manager fires
  `SIG_GLOBAL_UPDATE` so all dependent UI refreshes immediately.

#### Backward compatibility

- v3.2.1 behaviour is preserved end-to-end. The new global sensors,
  per-zone sensors, master-enable switch, and any-running binary sensor
  are all additive — none of them replace or shadow any existing v3.x
  entity. Existing automations and dashboards keep working unchanged.
- The kill switch is opt-in: if no entity is selected in the new
  Safety step of the options flow, the panic flow behaves exactly as it
  did in v3.2.1 (fires `EVENT_PANIC_REQUIRED`, creates a critical
  persistent notification, no direct upstream device control).
- Removing the dead schedule services means anyone who was calling them
  (no one — they were no-op stubs that logged "disabled in v3.0.0") will
  now get an `unknown service` error. Real schedule services with
  matching names land in alpha-2.
- The new `today_calculation` sensor reports `unknown` until the first
  valve has been discovered AND the periodic recalc has run (or
  `recalculate_now` has been called once). On a fresh install with no
  valves yet, this is expected.

#### What's still pending in v4.0

- **alpha-2** — `ScheduleEngine` (per-minute tick, sequential run queue,
  catch-up after restart), schedule CRUD services, `run_smart_now`,
  `run_schedule_now`, calculator integration with the engine, real
  data backing for `next_run_summary` and `schedules` sensors.
- **alpha-3** — `set_zone_*` extensions for fine-grained scheduling
  config; `skip_today` service.
- **alpha-4** — Per-zone run history persistence in the JSON store;
  history-driven charts; `week_summary` enrichment; rolling
  `avg_flow_lpm_7d` per zone.
- **alpha-5** — Pre-built storage-mode Lovelace dashboard YAML
  (4 tabs: Today / Schedule / Setup / Insight) shipped in
  `dashboards/z2m_irrigation.yaml`.
- **alpha-6** — Custom JS embed card (`<z2m-irrigation-embed-card>`)
  shipped in `www/`, registered as a Lovelace resource.
- **rc-1** — Edge cases, demolition guide for legacy helpers, polish.

## [3.2.1] - 2026-04-08

### 🐛 Hotfix — drop the dual-mode hardware backstop, simplify to single-mode
### 🐛 Hotfix — flip `auto_close_when_water_shortage` from ENABLE to DISABLE

The v3.2 happy-path test on a real device immediately after deploy revealed
two issues, both of which v3.2.1 fixes.

#### Issue 1 — `auto_close_when_water_shortage = ENABLE` breaks `cyclic_quantitative_irrigation`

When v3.2 first sees a valve, it pushes `auto_close_when_water_shortage =
ENABLE` to the device. v3.2 reasoning: it's a free hardware-level safety
net (device closes itself after 30 min of detected water shortage).

In testing on 2026-04-08:

- With `auto_close_when_water_shortage = DISABLE` (the default), the
  device's `cyclic_quantitative_irrigation` works correctly: send a target
  of N liters, device closes itself within ~2.5% of N liters.
- With `auto_close_when_water_shortage = ENABLE`, sending an
  `cyclic_quantitative_irrigation` command appears to be silently
  rejected: the device receives the command, the JSON shows the value,
  but the device's internal volume counter is left at zero. The valve
  opens but never closes on its own. (Likely a Sonoff firmware quirk
  where the two features compete.)

**Fix**: change the initial value to `DISABLE`. The integration actively
sets `DISABLE` on every newly-discovered valve at startup, undoing any
damage from a previous v3.2 install on the same device.

The "free 30-min water shortage safety net" is sacrificed for working
volume control. The integration's existing software guardrails (Layer 2
stuck-flow, Layer 3 MQTT silence, Layer 4 expected-duration warning,
v3.2 software 140% overshoot) collectively cover the failure modes that
the device-level feature would have caught.

#### Issue 2 — `cyclic_quantitative_irrigation` and `cyclic_timed_irrigation` are mutually exclusive

v3.2 published BOTH `cyclic_quantitative_irrigation` AND
`cyclic_timed_irrigation` in the same MQTT payload, expecting the device
to honor both simultaneously and "first to fire wins". An earlier dual-mode
test (50L volume + 30s time) confirmed the time backstop fired correctly,
which made it look like the design was sound.

Re-testing on 2026-04-08 with auto_close DISABLED revealed the truth:

- Combined payload (both fields in one JSON) → quantitative target
  silently dropped, only the time target is honored
- Sequential publishes (quantitative first, then time 2 seconds later)
  → same result, only the time target is honored
- Solo `cyclic_quantitative_irrigation` (no time at all) → works fine

**Conclusion**: the device's two cyclic modes are mutually exclusive on
this firmware. Setting one clears the other, regardless of payload
batching. The earlier 50L+30s test that "worked" actually only worked
because the time backstop fired first and we couldn't distinguish that
from "volume mode is also working".

**Fix**: remove the dual-mode design entirely. v3.2.1 publishes ONLY
`cyclic_quantitative_irrigation` from `start_liters()` and ONLY
`cyclic_timed_irrigation` from `start_timed()` (which was already its
behavior).

#### Removed in v3.2.1

- `_dispatch_start_liters()` — replaced by inline single-mode publish
- `_compute_time_backstop_seconds()` — no longer needed
- `_schedule_hw_backstop_refresh()` — no longer needed
- `_adaptive_hw_backstop_refresh()` — no longer needed
- `Valve.hw_time_backstop_seconds` field
- `Valve.hw_backstop_refresh_cancel` field
- Constants: `HW_TIME_BACKSTOP_OVERSHOOT_RATIO`,
  `HW_TIME_BACKSTOP_MIN_SECONDS`, `HW_TIME_BACKSTOP_MAX_SECONDS`,
  `HW_TIME_BACKSTOP_DEFAULT_FLOW_LPM`,
  `HW_TIME_BACKSTOP_REFRESH_INTERVAL_SECONDS`,
  `HW_TIME_BACKSTOP_REFRESH_SAFETY_PADDING_SECONDS`

#### Retained from v3.2 (still useful)

- ✅ Software 140% overshoot guardrail in `_on_state`
- ✅ Panic system: `_trigger_panic`, `_check_panic_conditions`,
  `clear_panic` service, `binary_sensor.z2m_irrigation_panic` with
  `restore_state`, `EVENT_PANIC_REQUIRED` / `EVENT_PANIC_CLEARED` events
- ✅ `current_device_status` monitoring + `EVENT_DEVICE_STATUS_CHANGED`
- ✅ Initial valve setup pushes `auto_close_when_water_shortage` (now
  set to `DISABLE` instead of `ENABLE`)

#### Net effect on safety

The morning's runaway scenario (Front Garden + Back Garden hit 956L
against a 324L target) was caused by the v3.1.x thread-safety bug, NOT by
the absence of a hardware time backstop. v3.1.2 fixed the thread-safety
bug. v3.2's hardware-quantitative-as-primary works correctly on its own
without the time backstop. So this simplification doesn't reduce real
safety — it just removes a complex and broken feature that was masking
the simpler working approach.

The Lilly Pilly "stuck flow sensor" failure mode is now caught by the
software stuck-flow guardrail (Layer 2, fires after 10 min of zero liter
progress), not by a hardware time backstop. That's the intended trade-off.

#### Files changed

- `custom_components/z2m_irrigation/manager.py` — strip helpers (~280 lines removed),
  simplify `start_liters` to single inline publish (~30 lines)
- `custom_components/z2m_irrigation/const.py` — remove HW_TIME_BACKSTOP_*
  constants, flip `INITIAL_VALVE_AUTO_CLOSE_WHEN_WATER_SHORTAGE` to `DISABLE`,
  update comments
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.2.1`

No DB schema changes. Backward compatible. Installs cleanly over v3.2.0.

---

## [3.2.0] - 2026-04-08

### 🏗️ Architectural shift — hardware-primary control

After v3.1.2 shipped this morning, a real-world incident exposed the limits
of software-only volume control: HA's flow integration is consistently
under-reporting actual delivered volume by 10–40% (depending on flow rate),
because the Sonoff SWV reports its `flow` field at only 1-decimal m³/h
precision. This meant the v3.1.x at-target software failsafe was firing
late or not at all in some scenarios.

A series of bench tests on 2026-04-08 with a measured bucket revealed:

- The device's `cyclic_quantitative_irrigation` hardware counter is
  **highly accurate** (~2.5% off vs bucket-measured ground truth).
- The device's `cyclic_timed_irrigation` hardware timer is accurate to ±2s
  and a new SET fully replaces the previous timer countdown.
- When BOTH `cyclic_quantitative_irrigation` AND `cyclic_timed_irrigation`
  are sent in the same MQTT payload, the device honours **both
  simultaneously** and **whichever fires first wins** (verified: a
  50L+30s combined run closed at ~30s).
- The device exposes `current_device_status` (`normal_state`,
  `water_shortage`, `water_leakage`) which the integration was ignoring.
- The device has `auto_close_when_water_shortage` (closes itself after
  30 min of detected water shortage) which was disabled.

Conclusion: shift to a **hardware-primary control architecture**. The
device's own features handle the precise close at exactly the requested
target. Software is now an observer + reporter + secondary safety net.

This fundamentally improves accuracy AND restart resilience: HA can crash,
reboot, lose MQTT, anything — the device still closes the valve when its
own counter says target is reached.

### ✨ New control flow

`start_liters(target)` now publishes ONE MQTT command containing BOTH:
- `cyclic_quantitative_irrigation: { irrigation_capacity: target }` —
  primary close mechanism. Device measures own flow, closes at target.
- `cyclic_timed_irrigation: { irrigation_duration: backstop_seconds }` —
  time-based safety backstop in case the volume mode gets stuck (e.g.
  blocked filter, dead flow sensor like the morning's Lilly Pilly issue).

The time backstop is calculated as
`(target_liters / historical_avg_flow) × HW_TIME_BACKSTOP_OVERSHOOT_RATIO (1.5)`,
clamped to `[HW_TIME_BACKSTOP_MIN_SECONDS (10 min), HW_TIME_BACKSTOP_MAX_SECONDS (4 hours)]`.
For valves with no historical data, falls back to
`HW_TIME_BACKSTOP_DEFAULT_FLOW_LPM (2 L/min)`.

### ✨ New: Adaptive hardware backstop refresh

Every `HW_TIME_BACKSTOP_REFRESH_INTERVAL_SECONDS` (5 min) while a session
is active, the integration recalculates the time backstop based on the
**current observed flow** and **remaining liters**, and republishes a
tighter timer if appropriate. As the run progresses, the safety window
narrows. By the end of a run, the backstop is tight enough that any real
problem gets caught within minutes.

Safety floor: the new published timer is always at least
`(REFRESH_INTERVAL + REFRESH_SAFETY_PADDING)` seconds in the future, so
a single missed refresh due to MQTT/network lag doesn't cause early
device closure.

### ✨ New: Software 140% overshoot guardrail

In v3.2 the device's quantitative_irrigation is the primary close. Software
no longer fires at 100% — it fires at **140% as the secondary defence**, in
case the device's hardware close failed AND flow is still being measured.

This is independent of the hardware backstop. If the hardware close
succeeds at exactly 100%, the software guardrail never triggers. If for any
reason the device flow keeps reading above the target, software intervenes
at 140%.

### ✨ New: Panic system

When the integration's normal failsafe mechanisms have been exhausted and
water may still be flowing, fire panic events that an external automation
can use to **kill an upstream device** (e.g., the main water pump). The
integration itself does NOT directly control any upstream device — it only
emits events. v4.0 will add a config field for an entity to turn off
automatically.

**Trip conditions:**
1. The OFF retry chain (5 min of escalating retries) has been exhausted
   and the device is still ON.
2. Two or more valves are simultaneously in shutoff_in_progress retry
   state for at least 60 seconds (indicates broader system failure).
3. The software 140% overshoot guardrail fired AND the device is still
   ON after `GUARDRAIL_SOFTWARE_OVERSHOOT_GRACE_SECONDS` (60s).

**Outputs:**
- New event: `z2m_irrigation_panic_required` (data: reason, affected_valves)
- New event: `z2m_irrigation_panic_cleared` (data: reason, elapsed)
- New entity: `binary_sensor.z2m_irrigation_panic` — turns ON when panic
  active. State persists across HA restart via `RestoreEntity`.
- Critical persistent notification.

**Manual clear:** new service `z2m_irrigation.clear_panic`. Optional
`cleared_by` parameter for audit logging. Wire this to a button/automation
of your choice.

### ✨ New: Device status monitoring

The Sonoff SWV's `current_device_status` field is now read on every MQTT
message. When it transitions away from `normal_state`, fire
`z2m_irrigation_device_status_changed` event so external automations can
alert the user to physical issues like water leakage or shortage.

This is what would have caught Lilly Pilly's blocked filter situation
this morning if we'd been watching the field.

### ✨ New: Initial device safety setup

When the integration first sees a valve, it pushes
`auto_close_when_water_shortage: ENABLE` to the device. This is a free
hardware-level safety net: the device closes itself after 30 min of
detected water shortage, regardless of HA's state.

### 🐛 Removed broken assumption

The previous AI's comment in `start_liters` claimed
"Sonoff SWV clears cyclic_quantitative_irrigation immediately after starting".
This is NOT true on Frigate firmware v4100 (current). The device honours the
quantitative target reliably. The comment was wrong; the architecture has
been changed accordingly.

### 📦 Files changed

- `custom_components/z2m_irrigation/const.py` — new constants section for
  v3.2 hardware-primary mode (~80 lines added). New `Platform.BINARY_SENSOR`.
- `custom_components/z2m_irrigation/manager.py` — new dual-mode start_liters
  (~250 lines), adaptive backstop refresh, software 140% guardrail, panic
  system, device status monitoring, initial valve safety setup (~580 lines
  added/changed)
- `custom_components/z2m_irrigation/binary_sensor.py` — **new file** —
  PanicSensor with restore_state
- `custom_components/z2m_irrigation/__init__.py` — register new
  `clear_panic` service
- `custom_components/z2m_irrigation/services.yaml` — describe new service
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.2.0`

No DB schema changes. Backward compatible — installs cleanly over v3.1.2.

### ⚠️ Known caveats

- **Stats accuracy**: software `session_used` will continue to under-report
  actual delivered volume by 10–40% depending on flow rate (this is the
  device's flow precision limit, not a bug). The dashboard numbers will
  look slightly low compared to what was actually delivered. The TOTAL
  volume delivered is correct because the device closes at the right
  target — only the per-message integration is imprecise.
- **The v3.2 design assumes the device honors `cyclic_quantitative_irrigation`
  reliably**. Bench-tested true on this firmware (v4100). If a future
  firmware breaks this, the software 140% guardrail and panic system are
  the safety nets.
- **Panic state survives restart** (via restore_state). To clear after
  resolving the underlying issue, call `z2m_irrigation.clear_panic`.

### 🧪 Test plan after merge

1. Tag `v3.2.0`, deploy, restart HA Core
2. Verify on startup: addon logs show "Pushed initial device safety:
   {valve} auto_close_when_water_shortage=ENABLE" for each valve
3. Verify `binary_sensor.z2m_irrigation_panic` is `off`
4. Run a small `start_liters(5)` test on Front Garden and watch the logs:
   - "🚿 Starting volume run" log line
   - "📤 Published dual-mode start" with both quantitative and time targets
   - Adaptive refresh ticks every 5 min (won't see this for short runs)
   - Clean session end at ~5L
5. Optionally trip the 140% guardrail by setting a smaller test target
   (e.g. 1L) on a fast-flow valve and watching it overshoot (would need
   to artificially block hardware close to truly test — skip unless
   carefully).

---

## [3.1.2] - 2026-04-08

### 🐛 Critical hotfix — thread-safety bug bricked the at-target failsafe

Real-world morning irrigation run on 2026-04-08 hit the bug. The smart
irrigation automation triggered Front Garden + Back Garden + Lilly Pilly
runs at sunrise. When Front Garden's volume hit its 324 L target, the
at-target failsafe in `_on_state` fired exactly as designed, set
`shutoff_in_progress = True`, logged the warning, and then **crashed
inside `hass.bus.async_fire(EVENT_SHUTOFF_INITIATED, …)`** with

```
RuntimeError: Detected ... non-thread-safe operation: ...
```

because `_on_state` is the MQTT message callback which runs from a
SyncWorker thread, not the HA event loop. HA's strict mode aborted the
call before the OFF retry chain could be scheduled.

Result: `shutoff_in_progress` was set to `True` (blocking subsequent
re-fires of the failsafe via the gate `if v.state == "ON" and not
v.shutoff_in_progress:`) but **no OFF was ever published to the device**.
Front Garden ran past its target indefinitely. Back Garden hit the same
code path and the same bug, ran ~3× target before manual intervention.

The Layer 1–4 guardrails in `_guardrail_tick` did NOT hit the bug because
that loop is registered via `async_track_time_interval` which always runs
on the event loop thread. The bug was specific to code paths called from
the MQTT worker thread:

| Call site | Thread | Affected? |
|---|---|---|
| `_initiate_shutoff` from `_on_state` (at-target failsafe) | SyncWorker | ❌ broken |
| `_initiate_shutoff` from `_guardrail_tick` (Layers 1-3) | MainThread | ✅ worked |
| State→OFF transition `EVENT_SHUTOFF_CONFIRMED` in `_on_state` | SyncWorker | ❌ broken |
| `_attempt_shutoff` `EVENT_SHUTOFF_FAILED` (via `async_call_later`) | MainThread | ✅ worked |
| `_create_persistent_notification` | depends on caller | ❌ broken when called from worker |
| Orphan recovery `EVENT_ORPHANED_SESSION_RECOVERED` (via `EVENT_HOMEASSISTANT_STARTED`) | MainThread | ✅ worked |

#### Fix

Two new helpers, both safe to call from any thread:

- **`_fire_event(event_type, event_data)`** — wraps `hass.bus.async_fire`
  via `hass.loop.call_soon_threadsafe`
- **`_create_persistent_notification`** — already existed, now wraps the
  whole `hass.async_create_task` + `services.async_call` chain via
  `loop.call_soon_threadsafe`

Every direct `self.hass.bus.async_fire(...)` call in `manager.py` is now
replaced with `self._fire_event(...)`. The in-thread-loop call sites that
weren't actually broken are also converted to use the helper, for
consistency and to prevent future regressions.

#### Files changed

- `custom_components/z2m_irrigation/manager.py` — add `_fire_event` helper,
  replace all 5 `hass.bus.async_fire` call sites, fix `_create_persistent_notification`
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.1.2`

No schema changes, no behaviour changes outside of "the failsafe now
actually fires". The 5 guardrails, OFF retry chain, and at-target failsafe
are otherwise identical to v3.1.1.

#### Note on data loss during this incident

The morning run lost an estimated ~600-1000 L of water across Front Garden
and Back Garden before manual `mqtt.publish` OFF intervention at 10:24
AEST. Lilly Pilly was unaffected by this bug (its session never reached
the at-target failsafe path) but had a separate physical flow blockage
that prevented water from reaching the plants — investigated separately.

---

## [3.1.1] - 2026-04-07

### 🐛 Hotfix — orphan recovery: defer side-effects until HA fully started

Real-world deployment of v3.1.0 against a production HA box found two related
bugs in `_recover_orphaned_sessions()`. Both have the same root cause and
both are fixed here.

#### What was wrong

`_recover_orphaned_sessions()` runs during `async_start()`, which executes
while Home Assistant is still in `CoreState.starting`. At that point:

- The MQTT integration is loaded but its **client may not be connected yet**
  — `mqtt.async_publish()` raises "The client is not currently connected".
- The `persistent_notification` integration may not have registered its
  service yet — `services.async_call("persistent_notification", "create", …)`
  silently no-ops.

The first deployment of v3.1.0 detected 91 legitimate orphan sessions
(accumulated from months of HA restarts before the fix existed) and:

- ✅ Successfully closed all 91 in the local SQLite DB.
- ❌ All 91 force-OFF MQTT publishes failed with "client not connected".
- ❌ The user-facing persistent notification was never created.

No real-world harm because the valves were physically OFF anyway, but the
**primary safety mechanism (force-OFF on restart) wasn't actually firing**
when it was needed most.

#### Fix — two-phase recovery

`_recover_orphaned_sessions()` is now split:

| Phase | When | What |
|---|---|---|
| **1 — DB cleanup** | `async_start()` (immediately) | Marks all orphan sessions as ended in the local SQLite DB. Pure local op, no external dependencies. |
| **2 — Force-OFF + notification** | `EVENT_HOMEASSISTANT_STARTED` (deferred) | Dedupe orphans by valve_topic, publish OFF once per unique valve via MQTT, fire one event per valve, create one summary persistent notification. |

The Phase 2 callback is registered via `hass.bus.async_listen_once()` for
the normal boot path, OR scheduled immediately if HA is already running
(config-reload edge case).

#### Bonus fix — dedupe orphans by valve_topic

The first v3.1.0 run logged ~91 OFF publishes for only 4 unique valves
(Front Garden alone had ~30 orphan sessions, mostly from past restarts).
Now we publish OFF **once per unique valve**, regardless of how many orphan
sessions belonged to it.

Persistent notification is also smarter: it shows up to 5 valve names
inline, then "and N more" for larger counts.

#### Files changed

- `custom_components/z2m_irrigation/manager.py` — split recovery into two
  phases; new imports for `CoreState` and `EVENT_HOMEASSISTANT_STARTED`.
- `custom_components/z2m_irrigation/manifest.json` — bump to `3.1.1`.

No schema changes. No new constants. No new behaviour outside the recovery
path. The 5 guardrails, OFF retry chain, and at-target failsafe from v3.1.0
are unchanged.

---

## [3.1.0] - 2026-04-07

### 🛡️ Safety release — multi-layered failsafe, OFF retry, restart recovery

This is a **safety-critical** release. The previous control loop had several
failure modes that could leave a valve running unbounded — see
[`AUDIT-2026-04-07.md`](./AUDIT-2026-04-07.md) for the full pre-fix audit.

All changes are surgical and contained to `manager.py`, `database.py`,
`const.py`, and the manifest. **No schema changes** to the SQLite database;
the new safety paths reuse the existing `sessions` table's `ended_at IS NULL`
semantics to identify in-flight sessions.

#### 🐛 Bugs fixed

- **CRITICAL — Volume target lost on HA restart.** Previously, if HA was
  restarted while a valve was physically open, the next MQTT `state: ON` from
  the device created a new in-memory session with `target_liters=None`, and
  the failsafe never fired. The valve could run unbounded until manual
  intervention.
- **CRITICAL — Runaway after primary failsafe.** Previously, when the at-target
  failsafe fired, it published OFF once with no retry, and immediately cleared
  `target_liters`. If the device failed to actually close (lost MQTT command,
  Zigbee delivery failure, firmware quirk), `session_liters` kept climbing
  indefinitely with no further failsafe — consistent with the user-reported
  "800 L target → 2000–3000 L actual" runaway.
- **CRITICAL — No MQTT-independent failsafe.** Previously, the at-target check
  ran ONLY inside `_on_state` (the MQTT message handler). If the device went
  silent (Zigbee dropout, dead battery), the failsafe never fired regardless
  of how much time had elapsed.
- **HIGH — No retry / verification of OFF.** Previously, OFF was published
  once with QoS 1 (broker-delivery only), with no acknowledgement check and
  no retry.

#### ✨ New: 5-layer safety guardrail loop

A new periodic loop runs every `GUARDRAIL_CHECK_INTERVAL_SECONDS` (30s) and
inspects every active session, completely independently of MQTT messages:

| Layer | What it catches | Default threshold |
|---|---|---|
| **1 — Volume overshoot** | Primary failsafe sent OFF but device kept flowing past target | `> target × 1.25` |
| **2 — Stuck flow** | Valve never opened, or flow sensor broken / reporting zero | `> 10 min` with no liter progress |
| **3 — MQTT silence** | Device went offline mid-run (Zigbee dropout, dead battery) | `> 5 min` since last MQTT msg |
| **4 — Expected duration warning** *(informational)* | Run is taking 50% longer than the historical average — possible clogged filter or pressure drop | `> historical_avg × 1.5` |
| **5 — Cross-restart recovery** | HA restarted mid-irrigation; orphaned session in DB | At every startup |

Layers 1–3 trigger the new shutoff retry chain. Layer 4 is informational only
(logs a warning + fires a HA event but does NOT force OFF). Layer 5 runs once
at startup, force-publishes OFF to all valves with orphaned in-flight
sessions, marks the sessions as completed in the DB, and creates a persistent
notification for the user.

All thresholds live in `const.py` and can be tuned without code changes.

#### ✨ New: OFF retry / confirmation state machine

When ANY guardrail (or the primary at-target failsafe) decides a valve must
shut off, the new `_initiate_shutoff()` / `_attempt_shutoff()` chain takes
ownership of the valve until the device confirms `state: OFF` or the retry
budget is exhausted. Schedule:

| Elapsed | Action |
|---|---|
| `T+0s` | Publish OFF (attempt 1) |
| `T+3s` | If still ON, publish OFF (attempt 2) |
| `T+8s` | If still ON, publish OFF (attempt 3) |
| `T+15s` | If still ON, publish OFF (attempt 4) — log WARNING |
| `T+30s` | If still ON, publish OFF (attempt 5) — **persistent notification** |
| `T+60s` → `T+300s` | Periodic retries |
| `T+300s` | Give up — fire `z2m_irrigation_shutoff_failed` event + **CRITICAL persistent notification** |

When the device finally reports `state: OFF`, the `EVENT_SHUTOFF_CONFIRMED`
event fires and the chain cleanly tears down. Idempotent: a second
`_initiate_shutoff` call while one is already in progress is silently ignored.

#### ✨ New: HA bus events for automation hooks

Three new HA events are fired so users can hook them in automations
(notifications, escalation, dashboards, etc.):

- `z2m_irrigation_shutoff_initiated` — fired when any guardrail/failsafe decides to OFF a valve
- `z2m_irrigation_shutoff_confirmed` — fired when the device finally confirms OFF
- `z2m_irrigation_shutoff_failed` — fired only after the entire 5-minute retry budget is exhausted
- `z2m_irrigation_orphaned_session_recovered` — fired at startup for each orphaned session found

#### ✨ New: Database method `get_in_flight_sessions()`

Added to `database.py` to support startup recovery. No schema changes — uses
the existing `WHERE ended_at IS NULL` query against the `sessions` table.

Also added `get_recent_avg_flow()` to support Layer 4 (expected duration
warning) — queries the last N completed sessions for a valve.

#### 🚧 Known issue (will be addressed in 3.1.1)

The duplicate session-end log line observed when manually toggling a valve
off (`Session ending ... 0.00min, 0.00L, 1.67lpm`) is a separate state-flap
issue — the device briefly toggles `state: ON → OFF → ON → OFF` in response
to the OFF command, which creates a second 60ms-long phantom session in the
DB. Cosmetic only, not a safety issue. Tracked separately.

#### 🛠️ Other changes

- `start_timed()` failsafe backup timer now also routes through the new
  retry chain instead of publishing OFF once.
- Added `recovered_from_orphan` field on `Valve` (currently used for log
  labelling only).
- All new constants are in `const.py` for easy tuning.
- Added [`AUDIT-2026-04-07.md`](./AUDIT-2026-04-07.md) — the full pre-fix
  audit and bug analysis.

---

## [3.0.6] - 2025-11-05

### 🐛 Critical Fix - Timezone Required for Last Session Start

#### Fixed Timezone-Aware Datetime
- **FIXED: Last Session Start timezone error** - Sensor now properly handles timezone-aware datetimes
  - **Error**: `ValueError: Invalid datetime: sensor provides state '2025-11-05 09:10:44.203866', which is missing timezone information`
  - **Problem**: Home Assistant timestamp sensors REQUIRE timezone-aware datetime objects
  - **Solution**: Added UTC timezone to parsed datetime objects
  - Imported `timezone` from datetime module
  - Check if datetime is naive (no timezone) and add UTC timezone
  - All timestamps now properly display with correct timezone info

---

## [3.0.5] - 2025-11-05

### 🐛 Bug Fix - Last Session Start Sensor

#### Fixed Timestamp Display
- **FIXED: Last Session Start showing "Unknown"** - Sensor now properly displays timestamp
  - **Problem**: Home Assistant's timestamp device class requires datetime object, not ISO string
  - **Error**: Sensor was throwing exception when updating, causing "Unknown" display
  - **Solution**: Parse ISO datetime string to Python datetime object in native_value property
  - Handles missing data gracefully (returns None)
  - Includes error handling for malformed dates

---

## [3.0.4] - 2025-11-05

### ✨ New Sensor - Last Session Start

#### Last Session Start Datetime
- **NEW: Last Session Start sensor** - Shows the start datetime of the most recent completed session
  - Displays as a timestamp in Home Assistant
  - Updates automatically when session ends
  - Also updates during periodic 15-minute refresh
  - Useful for tracking when irrigation last ran
  - Stored in database, persists across restarts
  - Returns `None` if no sessions recorded yet

---

## [3.0.3] - 2025-11-05

### ✨ Enhancement - Automatic Time-Based Sensor Updates

#### Periodic Refresh for 24h/7d Sensors
- **NEW: Automatic periodic refresh** - 24h and 7d sensors now update automatically every 15 minutes
  - **Problem**: Sensors only updated when valve was triggered, causing stale data
  - **Example**: Old sessions would remain counted past 24h until next valve use
  - **Solution**: Added periodic background refresh every 15 minutes
  - Sensors now stay accurate without requiring manual valve triggering
  - Uses Home Assistant's `async_track_time_interval` for reliable scheduling

---

## [3.0.2] - 2025-11-04

### 🐛 Critical Bug Fix - Time-Based Sensors

#### 24h/7d Calculation Fix
- **CRITICAL FIX: 24h and 7d sensors showing incorrect values** - Fixed database queries for time-based metrics:
  - **Problem**: Queries were using `started_at >= cutoff` which only counted sessions that *started* within the time window
  - **Result**: Sensors were showing cumulative totals instead of rolling time windows
  - **Solution**: Changed to `ended_at >= cutoff` to correctly count sessions that *completed* within the time window
  - Both 24h and 7d sensors now accurately show rolling window usage

---

## [3.0.1] - 2025-11-02

### 🐛 Critical Bug Fixes

#### Race Condition Fixes
- **CRITICAL FIX: Session tracking race conditions** - Fixed multiple race conditions:
  1. **Session ID capture bug**: Session IDs were being cleared before async database operations completed, resulting in `session_id=None` in logs and NULL `ended_at` in database. Now captures all session values before clearing them.
  2. **Sensor initialization race**: Sensors were showing `0.0` on restart because they were created before valve data loaded from database. Now loads all metrics BEFORE announcing valve to sensor platform.

---

## [3.0.0] - 2025-11-01

### 🎉 MAJOR RELEASE - 100% Local Persistence

#### Bug Fixes (Nov 1, 2025)
- **CRITICAL FIX: Session tracking race conditions** - Fixed multiple race conditions:
  1. **Session ID capture bug**: Session IDs were being cleared before async database operations completed, resulting in `session_id=None` in logs and NULL `ended_at` in database. Now captures all session values before clearing them.
  2. **Sensor initialization race**: Sensors were showing `0.0` on restart because they were created before valve data loaded from database. Now loads all metrics BEFORE announcing valve to sensor platform.
- **CRITICAL FIX: Sessions not ending properly** - Fixed race condition where `current_session_id` was set AFTER async database save, causing sessions to not be recorded if valve turned off quickly. Now generates session_id immediately when valve turns ON.
- Fixed MQTT connection timing issue on startup (graceful handling if MQTT not ready)
- Fixed `async_add_entities` RuntimeError by adding @callback decorator to entity addition functions
- Fixed missing `_LOGGER` import in `__init__.py`
- Fixed SQLite concurrent access issues by enabling WAL mode
- Fixed SQLite query handling for NULL results in 24h/7d usage calculations - added explicit None checks before float conversion
- **Fixed SQLite "bad parameter or other API misuse" errors** by:
  - Using `connection.execute()` directly instead of creating cursors (better thread safety in Home Assistant's executor)
  - Adding explicit string conversion for all parameters
  - Adding parameter validation and type checking
  - **Added threading.Lock to protect all database operations** - prevents race conditions in Home Assistant's executor thread pool
- **Added COMPLETE debug logging** - Every database operation, manager action, and session tracked with ➡️/⬅️ arrows (see DEBUGGING-24H-7D.md)
- Integration now loads successfully even if MQTT connects after integration startup

#### Breaking Changes
- **Removed Supabase cloud dependency** - All data now stored locally in SQLite
- **Scheduler temporarily disabled** - Smart schedules require database migration (coming in v3.1.0)
  - Manual watering via services (`start_liters`, `start_timed`) works perfectly
  - Use automations for scheduling in the meantime
- No more .env file needed
- No more external configuration
- Fully local, no internet required

#### New Features

**Local SQLite Database**
- All irrigation data stored in `/config/z2m_irrigation.db`
- Automatic initialization on startup
- Survives all Home Assistant restarts
- Auto-cleanup of old sessions (>90 days)
- Included in Home Assistant backups automatically

**4 New Time-Based Sensors Per Valve**
- `sensor.xxx_last_24h` - Liters used in last 24 hours
- `sensor.xxx_last_24h_minutes` - Runtime in last 24 hours
- `sensor.xxx_last_7_days` - Liters used in last 7 days
- `sensor.xxx_last_7_days_minutes` - Runtime in last 7 days

**Universal Session Tracking**
- Tracks ALL valve usage regardless of trigger source:
  - Integration service calls
  - Manual switch toggles
  - Automations
  - Z2M manual control
  - Physical valve button
- Rolling time windows (24h, 7d) update after every session
- Complete history preserved

#### Improvements
- Faster startup (no external API calls)
- Better reliability (no network dependency)
- Simpler setup (no cloud configuration)
- Enhanced debug logging with emojis
- Better performance with indexed queries

#### Migration
- Existing data from v2.x not migrated (fresh start)
- All sensors remain compatible
- No configuration changes needed
- Just restart Home Assistant!

See `LOCAL-PERSISTENCE-GUIDE.md` for complete documentation.

---

## [2.0.0] - 2025-10-20

### 🎉 MAJOR RELEASE - Smart Scheduling System

#### New Features: Irrigation Scheduling

**Time-Based Schedules**
- Create schedules that run at specific times (e.g., 6:00 AM, 6:00 PM)
- Select specific days of the week or run daily
- Set duration (minutes) or volume (liters) targets
- Enable/disable schedules without deleting them

**Interval-Based Schedules**
- Run valves every X hours automatically
- Perfect for frequent watering needs
- Tracks last run time automatically

**Smart Conditions (Weather-Aware)**
- Skip if soil moisture is too high (sensor integration)
- Skip based on temperature ranges (weather integration)
- Skip if it rained recently (weather integration)
- Conditions are optional - simple schedules work too!

**Database Backend**
- All schedules stored in Supabase
- Schedule run history tracked automatically
- View why schedules were skipped (conditions, manual, etc.)
- Link schedule runs to irrigation sessions

#### New Services

- `z2m_irrigation.create_schedule` - Create new schedule
- `z2m_irrigation.update_schedule` - Modify existing schedule
- `z2m_irrigation.delete_schedule` - Remove schedule
- `z2m_irrigation.enable_schedule` - Enable schedule
- `z2m_irrigation.disable_schedule` - Disable schedule
- `z2m_irrigation.run_schedule_now` - Trigger schedule immediately
- `z2m_irrigation.reload_schedules` - Reload from database

#### WebSocket API

- `z2m_irrigation/schedules/list` - Get all schedules
- `z2m_irrigation/schedules/get` - Get specific schedule
- `z2m_irrigation/schedules/runs` - Get schedule run history

#### Architecture Changes

- New `scheduler.py` module handles all scheduling logic
- Checks for due schedules every minute
- Automatic next-run-time calculation
- Priority system for overlapping schedules
- Thread-safe execution

**Breaking Changes:**
- `hass.data[DOMAIN][entry_id]` now returns `{"manager": ..., "scheduler": ...}` instead of just the manager

---

## [1.0.3] - 2025-10-20

### 🚨 CRITICAL - Threading Fixes

#### Thread Safety Violations Fixed
- **FIXED**: All threading violations causing Home Assistant crashes
  - Added `_schedule_task()` helper for thread-safe async task scheduling
  - Fixed `_on_state()` MQTT callback to use `call_soon_threadsafe()`
  - Added `@callback` decorator to all entity update callbacks
  - Entities (sensor/switch/number) now update safely from dispatcher signals

#### Failsafes Now Actually Work
- **CONFIRMED**: Failsafes detected 12L/5L overflow and tried to stop valve
  - Previous threading errors prevented OFF command from executing
  - Now properly sends OFF command when targets exceeded
  - Uses thread-safe task scheduling

**Critical upgrade**: v1.0.2 had the logic but threading bugs prevented execution. v1.0.3 actually works!

---

## [1.0.2] - 2025-10-20

### 🐛 Critical Fixes - Device Quirk Discovered

#### Device Clears Native Volume Commands
- **DISCOVERED**: Sonoff SWV clears `cyclic_quantitative_irrigation` immediately after starting
  - Z2M logs show: device accepts command, sets `current_count:1`, valve turns ON
  - Then immediately: `irrigation_capacity:0, total_number:0` (program cleared!)
  - **Solution**: Use simple ON/OFF + HA monitoring for volume runs
  - Timed runs: Testing needed to see if `cyclic_timed_irrigation` has same issue

#### Failsafe System Fixes
- **FIXED**: Failsafes now check on EVERY MQTT update, not just during flow integration
  - Volume failsafe now triggers even if flow stops or is zero
  - Time failsafe now checks anytime valve is ON with a target time
  - Added progress logging (DEBUG level) to track volume runs
  - Failsafes clear targets after triggering to prevent repeated OFF commands

#### Switch State Delay
- **DOCUMENTED**: Switch entity updates when Z2M publishes state, not instantly
  - This is normal Zigbee behavior (device → coordinator → Z2M → MQTT → HA)
  - Typical delay: 1-3 seconds
  - State eventually syncs correctly

---

## [1.0.1] - 2025-10-20

### 🐛 Critical Fixes

#### Volume-Based Runs Not Stopping
- **FIXED**: Added automatic valve shutoff when target liters reached
  - Integration now actively monitors flow and turns off valve when target is reached
  - Prevents overwatering that was occurring in v1.0.0
  - Added detailed logging when volume target is reached

#### Native Device Commands Fixed
- **CORRECTED**: Now using proper `cyclic_quantitative_irrigation` and `cyclic_timed_irrigation` objects
  - Previous attempts used wrong parameters: `water_consumed`, `timer` (not supported)
  - Now using correct Z2M API per device documentation
  - Device will handle shutoff natively + HA backup monitoring as failsafe

#### Flow Conversion Clarified
- **DOCUMENTED**: Device reports flow in m³/h, not L/min
  - Conversion: 1 m³/h = 16.667 L/min
  - `flow_scale` is a user multiplier (default 1.0)

### Technical Details

**What Was Wrong:**
- Using `{"state": "ON", "water_consumed": 6000}` ❌ (Z2M: "No converter available")
- Using `{"state": "ON", "timer": 360}` ❌ (Z2M: "No converter available")

**What's Correct:**
- Volume: `{"cyclic_quantitative_irrigation": {"current_count": 0, "total_number": 1, "irrigation_capacity": 6, "irrigation_interval": 0}}` ✅
- Timed: `{"cyclic_timed_irrigation": {"current_count": 0, "total_number": 1, "irrigation_duration": 360, "irrigation_interval": 0}}` ✅

### How It Works Now - Triple Failsafe System

**Volume Runs (3 layers of protection):**
1. **Native Device Control**: `cyclic_quantitative_irrigation` command tells device to stop at target
2. **Real-time Monitoring**: HA checks every MQTT update if `session_liters >= target_liters`
3. **Forced Shutoff**: If target exceeded, HA sends OFF command immediately (logged as WARNING)

**Timed Runs (3 layers of protection):**
1. **Native Device Control**: `cyclic_timed_irrigation` command tells device to stop at target time
2. **Real-time Monitoring**: HA checks every MQTT update if `now >= session_end_ts`
3. **Backup Timer**: HA timer fires at exact target time and forces OFF if still running (logged as WARNING)

**Result**: Even if the device completely fails, HA will ALWAYS turn off the valve when targets are reached.

**⚠️ Upgrade immediately if using volume-based irrigation!**

---

## [1.0.0] - 2025-10-20

### 🎉 Major Release

Complete rewrite with enhanced features and local database integration.

### ✨ Added

- **Session Duration Sensor** - Track how long the current irrigation session has been running
- **Dual Remaining Sensors** - Separate sensors for remaining time and remaining liters with smart estimates
- **Native Zigbee Control** - Commands sent directly to device for offline operation
  - Timed runs use device's built-in timer
  - Volume runs use device's built-in water meter
- **Local Database Integration** - Session history stored in Home Assistant's recorder (no cloud required)
- **Battery Level Sensor** - Monitor valve battery status
- **Link Quality Sensor** - Track Zigbee signal strength
- **Session Count Sensor** - Total number of irrigation sessions
- **Number Entities** - Easy-to-use controls for setting run duration and volume
- **Enhanced Documentation** - Comprehensive README and installation guide

### 🔧 Changed

- **Unit Conversion Fixed** - Properly converts m³/h to L/min (multiply by 16.667)
- **Flow Rate Accuracy** - Corrected flow rate calculations for Sonoff SWV devices
- **Threading Issues Resolved** - Fixed all async/await patterns to prevent event loop errors
- **Session Tracking Improved** - Better session start/end detection and logging
- **Reset Service Enhanced** - Now also resets session count

### 🗑️ Removed

- **Supabase Dependency** - Replaced with native Home Assistant database
- **Cloud Dependencies** - All data stored locally
- **Unnecessary Files** - Cleaned up non-integration files from repository

### 📊 Technical Improvements

- Home Assistant recorder integration for long-term statistics
- Proper async/await patterns throughout codebase
- Better error handling and logging
- Optimized MQTT message processing
- Improved device discovery reliability

### 📚 Documentation

- Complete README with features, installation, and troubleshooting
- Detailed installation guide with HACS and manual methods
- Service examples and usage patterns
- Dashboard customization examples
- Troubleshooting section with common issues

---

## [0.9.2] - Previous Version

### Features

- Basic valve control via MQTT
- Flow rate monitoring
- Session tracking
- Total usage counters
- Timed run support
- Volume run support

---

## Migration from 0.9.x to 1.0.0

### Breaking Changes

None - this version is fully backward compatible!

### What You Get

After upgrading, you'll see these new entities per valve:
- `sensor.{valve}_session_duration`
- `sensor.{valve}_remaining_time`
- `sensor.{valve}_remaining_liters`
- `sensor.{valve}_battery`
- `sensor.{valve}_link_quality`
- `sensor.{valve}_session_count`
- `number.{valve}_run_for_minutes`
- `number.{valve}_run_for_liters`

Old entities remain unchanged:
- `switch.{valve}_valve`
- `sensor.{valve}_flow`
- `sensor.{valve}_session_used`
- `sensor.{valve}_total`
- `sensor.{valve}_total_minutes`

### Upgrade Steps

1. Update via HACS or replace files manually
2. Restart Home Assistant
3. All new sensors will appear automatically
4. Update your dashboards to include new entities
5. Session history starts logging immediately

---

**Note**: This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.
