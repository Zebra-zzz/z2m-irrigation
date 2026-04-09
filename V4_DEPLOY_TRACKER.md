# v4.0 Deploy Tracker

> **Last update: 2026-04-09 ~10:00 Melbourne** — see "Append-only event log"
> at the bottom for the chronology.

Live issue + work tracker for the v4.0 rollout. Maintained as we go so
nothing falls off when we context-switch. Update in place — strike out
done items, add new ones at the bottom of each section.

---

## 🔥 In flight right now

| # | Item | Status |
| --- | --- | --- |
| 1 | rc-2 weather.py unit-aware conversion deployed to HA | **VERIFY** — restart finished, need to confirm `today_calculation` dropped from 172.8 L → ~108 L |

---

## 🐛 Known bugs / issues to fix

### Integration / backend

| # | Severity | Issue | Notes / next step |
| --- | --- | --- | --- |
| ~~B1~~ | ~~CRITICAL~~ | ~~VPD read in hPa, treated as kPa, calculator over-watering by 60%~~ | ✅ FIXED in rc-2 (`weather.py` unit-aware conversion). Verified live: 172.8 L → 108.03 L. |
| **B2** | **HIGH** | `z2m-irrigation-schedule-editor-card.js` stored zone identifiers as the slugified `entity_id` (e.g. `front_garden`) instead of the valve's `friendly_name` (e.g. `Front Garden`). The integration's engine keys `mgr.valves` by `friendly_name`, so a slug-form schedule resolved to zero zones at fire time and got stamped `skipped_no_zones`. Affected the user's first "Test" schedule. | ✅ FIXED — `_discoverZones()` now uses `friendly_name` for both `id` and `name`. Card version bumped to 4.0.0rc2. Synced to HA. The user's existing Test schedule was repaired in-place via the `update_schedule` service. |
| B3 | LOW | `unique_id` / `_attr_name` mismatch on global sensors causes HA to generate entity_ids without the `_summary` suffix the unique_id implies. Caused D4 above. | Long-term: rename either the unique_id (drop `_summary`) or the friendly name (add `Summary`) so they match. Doesn't affect runtime behaviour after D4 was fixed in the dashboard YAML. Rename should land in rc-3 to keep entity_ids stable for new installs. |
| **B5** | **HIGH** | `Valve.last_session_liters` is set in `_end_and_sync` after a session ends, but **NEVER loaded from the database on startup**. After every HA restart, the field is `None` until a new session ends, so the per-zone tile metric reads `— L` even though the SQLite session history has the data. Same issue affects the per-zone `last_run_liters` sensor. The user reported the dashboard shows "— L" for all 4 zones after a restart, even though their last sessions were a few hours ago. | Add `IrrigationDatabase.get_last_session(valve_topic)` returning the most recent completed session row, and call it from `_ensure_valve._sub()` alongside the existing 24h/7d aggregate loads. Populate `valve.last_session_liters` from the result. Ship as rc-3 backend patch. |
| B4 | LOW | Two `z2m_irrigation.<config_entry_id>` files in `.storage/`: `01K8DXZB195QE3MWPEN14K46KX` (0 schedules, stale) and `01KNQKPVTYRZYA4YVM36TVC4HE` (1 schedule, active). The stale one is from a previous config-entry that was removed but its store file wasn't cleaned. | Cleanup: delete the stale file via `sudo rm`. Doesn't affect runtime — HA only loads the file matching the active entry_id. Deferred to cleanup phase. |

### v4.0 dashboard (`/dashboard-z2m/today`)

| # | Severity | Issue | Root cause | Fix |
| --- | --- | --- | --- | --- |
| ~~D1~~ | ~~HIGH~~ | ~~Hero card crash on null state access~~ | ~~Missing null guards~~ | ✅ FIXED — null-guard pattern applied to all 3 templates |
| ~~D2~~ | ~~HIGH~~ | ~~auto-entities + grid: Invalid configuration~~ | ~~auto-entities filter races with entity registry warmup, returns 0 matches → empty cards array → grid setConfig crash~~ | ✅ FIXED — replaced ALL 4 auto-entities instances (per-zone tiles, manual sliders, in_smart_cycle list, avg flow strip) with hardcoded entries for the 4 known valves |
| ~~D3~~ | ~~HIGH~~ | ~~auto-entities + vertical-stack on Schedule tab~~ | ~~Same root cause as D2~~ | ✅ FIXED — schedule list converted to a single Jinja markdown table with explicit empty-state branch |
| **D4** | **CRITICAL** | Dashboard references `sensor.z2m_irrigation_next_run_summary` but the actual entity_id HA generated is `sensor.z2m_irrigation_next_run` (similarly `_active_session_summary` → `_active_session`) | The integration sets `_attr_unique_id = "..._summary"` but `_attr_name = "...Next Run"` (no "summary"). HA generates `entity_id` from the **friendly name**, so the slug becomes `z2m_irrigation_next_run` — `summary` is dropped because it's not in the friendly name. The dashboard YAML used the unique_id-shaped name and was reading a non-existent entity. | ✅ FIXED — sed-replaced all 13 references in the dashboard YAML to use the actual entity_ids. (Long-term: also fix the integration source to reconcile unique_id and friendly_name — see B3 below.) |
| **D6** | **CRITICAL** | Per-zone tile hardcoded `entity: switch.front_garden` etc. but the actual entity_id is `switch.front_garden_valve` (my integration's `ValveSwitch` uses `_attr_name = "Valve"` which suffixes the entity_id with `_valve`). Same issue for all 4 zones. The user's z2m integration ALSO exposes switches as `switch.<zone>` without the `_valve` suffix for 3 of the 4 zones (back_garden, lilly_pilly, mains_taps), so 3 tiles "worked" but used the wrong switch (the z2m one, not mine), and the front_garden tile read an entity that doesn't exist. | Fix: change all 4 hardcoded switch refs in the per-zone tile section + manual run section to use `switch.<zone>_valve`. Apply in next dashboard pass. |
| **D7** | **HIGH** | Hero card shows only ONE running valve when multiple are running in parallel. User reported: started Front Garden manual run → Hero showed Front Garden. Then started Lilly Pilly in parallel → Hero card unchanged, still showing only Front Garden. | The Hero card reads `sensor.z2m_irrigation_active_session` which only tracks one session at a time (it was designed for the sequential queue runner). Fix: read `binary_sensor.z2m_irrigation_any_running.attributes.running_valves` instead, which is a list of all currently-active valves. Show count + names + combined liters. |
| **D8** | **HIGH** | No way to **stop a manual run** from the dashboard. User had to open Z2MQTT and turn off the valve manually. | Multiple fixes needed: (1) per-zone tile becomes tap-to-stop when its valve is `on`, with a confirmation dialog. (2) Hero card running state shows a prominent "🛑 Stop all running" button that iterates `running_valves` and calls `switch.turn_off` on each `<zone>_valve` switch. (3) The manual run section should add a "Stop" button next to each slider when its valve is active. |
| **D9** | **HIGH** | **Per-zone tile metric only updates AFTER the run completes**, not live during the run. So during a manual run there's no live "X / Y L delivered" feedback in the tile — it just shows the last completed run's volume. | The tile metric reads `sensor.<zone>_last_run_liters` which is end-of-session data. Fix: when the valve switch is `on`, read `sensor.<zone>_session_used` (the LIVE running total) plus `sensor.<zone>_flow` (current L/min) plus `sensor.<zone>_remaining_liters` (target − used) to render a live progress display. Fall back to `_last_run_liters` when the valve is `off`. |
| D5 | LOW | "Next scheduled run" header card on Schedule tab renders as a small empty bar when there are no schedules (or before D4 was fixed, when next_run wasn't reading the right entity) | Markdown card with one line of text inside a card frame looks empty | Improve the empty-state markdown OR drop the wrapping card and inline the content. Polish-only. |

### User's Mount Cottrell · Ecowitt GW2000C dashboard

| # | Severity | Issue | Root cause | Fix |
| --- | --- | --- | --- | --- |
| M1 | MEDIUM | All "VPD … kPa" displays show the raw hPa value mislabelled as kPa (so e.g. "9.38 kPa" when actual VPD is 0.94 kPa). Color thresholds also wrong because they compare hPa raw against kPa thresholds. | Dashboard hardcodes `kPa` label on the raw `sensor.gw2000c_vapour_pressure_deficit` value without dividing by 10. | Either (a) edit each VPD reference in the dashboard to `\| float / 10`, or (b) use the new template sensor we'd build for this, or (c) just keep the raw label as `hPa`. |
| M2 | LOW | Pressure trend chart `lower_bound` not set; might rescale weirdly during stable weather | Pre-existing | Optional polish |

---

## 🚧 Feature gaps surfaced during the rollout

| # | Priority | Feature | Notes |
| --- | --- | --- | --- |
| F-A | HIGH | **Per-zone factor / l_per_mm / base_mm editor in the Setup tab** | Currently the Setup tab tells the user to call `z2m_irrigation.set_zone_factor` from Developer Tools. The user explicitly asked "is there no way to influence the smart schedule by telling it I want more water in a certain zone?" — so the discoverability is failing. Build a section with 4 rows (one per zone), each row showing current factor + l_per_mm + base_mm with a +/- pair that calls the corresponding service. Could be a `mushroom-template-card` per row OR a small custom JS card. Targeted for the next dashboard polish pass. |
| F-B | HIGH | **Sunrise / sunset relative schedule times** | Currently `Schedule.time` is a hardcoded `HH:MM` string. The user's legacy v3.x setup had an automation called "Irrigation — set next smart time (sunrise − 45m)" — they want this back. Two implementation paths: (1) extend `Schedule.time` to accept `sunrise-45m` / `sunset+30m` syntax and have the engine resolve via `sun.sun.next_rising` each tick. (2) Keep the time field strict and add a separate `time_offset_from_sun` field. Path 1 is more user-friendly. Targets v4.1. **Workaround now**: keep the schedule disabled and use a small HA automation that triggers at `sunrise -00:45:00` and calls `z2m_irrigation.run_schedule_now` with the schedule's id. |
| F-C | MEDIUM | **In-dashboard schedule edit** (rename, change time, change days, change zones) | The schedule editor JS card only does CREATE. To edit an existing schedule the user has to call `z2m_irrigation.update_schedule` from Developer Tools. Build edit-mode into the card, OR ship a separate "edit existing schedule" card. Targets v4.1. |
| F-D | MEDIUM | **Tap-to-run / hold-to-toggle on schedule rows** | The Schedule tab currently shows the list as a markdown table — no per-row interactivity. The previous auto-entities + mushroom-template-card pattern had this but auto-entities was unreliable. v4.1: ship a custom JS card for the schedule list with per-row buttons. |
| F-E | LOW | **Auto-discovery of new valves in the dashboard** | After hardcoding the 4 known valves to fix D2, the dashboard no longer adapts when a new valve is added. To add a 5th valve the user has to copy a stanza in the YAML. v4.1: ship a custom JS card for per-zone tile rendering that pulls from the live integration without depending on auto-entities. |
| **F-I** | **HIGH** | **Session Log tab** — the user wants a Log tab showing all runs in a table with start/stop times, trigger type (`schedule` / `manual_volume` / `manual_timed`), starting parameters (`target_liters` / `target_minutes`), and final delivered values when stopped (`actual_liters` / `actual_duration`). All this data already lives in the SQLite `sessions` table — just needs to be exposed as an HA entity and rendered. Build path: (1) new `IrrigationDatabase.get_recent_sessions(limit=200)` method, (2) new global sensor `sensor.z2m_irrigation_session_log` whose `sessions` attribute carries the most recent N rows, refreshed on session-end + on startup, (3) new "Log" tab in the dashboard with a markdown card rendering the sessions list as a table via Jinja. Ship as rc-3. |
| **F-J** | **HIGH** | **No way to edit or delete existing schedules from the dashboard** — the schedule editor JS card only does CREATE. To edit or delete, the user has to call `z2m_irrigation.update_schedule` / `delete_schedule` from Developer Tools with the schedule_id. The user explicitly asked for this. Build: enhance the existing `z2m-irrigation-schedule-editor-card.js` with (a) a list view at the top showing all existing schedules with Edit + Delete buttons per row, (b) an edit mode that pre-fills the form with the selected schedule's values and submits via `update_schedule` instead of `create_schedule`, (c) a delete confirmation dialog. ~200 lines of new JS in the card. Bump card version to rc-3. Ship alongside B5 + F-I. |
| F-F | MEDIUM | **Manual run section needs both timed AND volume sliders** | Currently the Today tab "Manual run" section only has 4 `number.<zone>_run_for_liters` sliders (volume-based). The integration also has `number.<zone>_run_for_minutes` (time-based) entities created by `number.py`, but they're not exposed in the dashboard. Add 4 more slider rows for time-based runs, OR group them by zone with a "L \| min" toggle. The user explicitly asked for both options. Quick fix — just add the 4 minute-sliders alongside the existing liter-sliders in the manual run section. |
| **F-H** | **HIGH** | **Three-knob model is over-engineered for the dashboard UI** — `factor`, `l_per_mm`, `base_mm` are all multipliers in the final liters calc. Mathematically they collapse to one number, but conceptually they answer different questions: `base_mm` = plant water demand (set once based on agronomy), `l_per_mm` = zone area in m² (set once via bucket test or measurement), `factor` = the daily-driver "more/less" knob. The current Setup tab editor (built in F-A) treats all three with equal weight, which is confusing. **Resolution decided**: Option C — keep three-knob backend (correct math), simplify the UI to show only `factor` ➖➕ buttons by default with `l_per_mm` and `base_mm` collapsed under "Calibration (advanced)" at the bottom of the Setup tab. Pending user confirmation before executing the simplification. **Also pending**: rc-3 backend rename `l_per_mm` → `area_m2`, `base_mm` → `water_per_day_mm` to make the meaning obvious without docs. Schema migration v1 → v2 in ZoneStore. |
| **F-G** | **HIGH** | **VPD time-of-day sampling bias** — calculator reads VPD as a single-point snapshot at fire time. For early-morning schedules (e.g. user's 08:53 Test schedule), VPD has barely started rising and is well below the day's peak. The calculator sees `0.94 kPa → dryness 1.16 → 27 L/zone`, but if it ran at 14:00 it would see `~2.0 kPa → dryness 1.5 (capped) → 36 L/zone` — i.e. the integration is **undercounting day-total ET demand by ~30%** for any morning schedule. Rain inputs are already time-windowed (user's `gw2000c_24h_rain` is a 24h rolling sum, BoM forecast is forward-looking), only VPD is point-in-time. **Workaround for now (Option A from the discussion):** create a `statistics` template sensor with `state_characteristic: mean` and `max_age: 24h` over the existing VPD sensor, then point the integration's VPD config at the new averaged sensor. The integration's rc-2 unit-aware conversion handles the inherited `hPa` unit correctly. **Proper fix (v4.1 candidate):** add internal VPD sampling to the integration — take a reading every ~15 min via the existing `_periodic_recalculate_today` loop, keep a rolling 24h buffer keyed on monotonic timestamps, expose a config option `vpd_averaging_window: 24h` (or similar) that switches the calculator from `state.state` to `mean(buffer)`. Cold-start has no history so falls back to instantaneous until the buffer fills. Decision pending. |

---

## 🌍 Real-world device alerts (NOT deploy regressions)

| # | Severity | Issue | Notes |
| --- | --- | --- | --- |
| R1 | HIGH | **Back Garden** Sonoff valve reported `water_shortage` post-restart on 2026-04-09 ~08:23 | Hardware sensor on the valve. Check water supply pressure at the valve, filter, supply line. Not caused by the deploy. |
| R2 | HIGH | **Lilly Pilly** Sonoff valve reported `water_shortage` post-restart on 2026-04-09 ~08:24 | Same — physical inspection needed. The user previously fixed Lilly Pilly's clogged filter. May have re-clogged or there's a separate issue. |

---

## 📦 Pending v4.0 milestones

| # | Item | When |
| --- | --- | --- |
| P1 | Smoke-test the schedule editor card (create one schedule, force-fire, verify queue runner) | Whenever convenient |
| P2 | Soak rc-2 for ~1 week of normal runs | After D1/D2/D3 fixed |
| P3 | Walk through DEMOLITION.md to tear down legacy v3.x helpers/scripts/automations | After P2 |
| P4 | Bump manifest from `4.0.0rc2` → `4.0.0` final | After P3 (or P2 if user defers demolition) |

---

## 🧹 Cleanup

| # | Item | Status |
| --- | --- | --- |
| C1 | Delete `/config/restore_work/` (4.2 GB Apr-8 backup tar + extracted files + restore script) on HA | Pending (after rc-2 verified) |
| C2 | Remove `restore_dashboard.py` from `/config/` on HA | Pending |
| C3 | Verify `/config/z2m_irrigation_backups/z2m_irrigation.v3.2.1.bak.20260409-080050` is the only rollback artifact and decide whether to keep it long-term | Pending |

---

## 🗂 Deferred (unrelated to v4.0)

| # | Item | Notes |
| --- | --- | --- |
| F1 | Tesla automation post-deploy verification | When car next plugs in / unplugs |
| F2 | `supported: false` flag investigation | Pre-existing |
| F3 | HA recorder → MariaDB migration | Pre-existing |
| F4 | Memory pressure recheck post-trim | Pre-existing |
| F5 | Tuya integration overlap audit | Pre-existing |
| F6 | Move secrets to `secrets.yaml` + rotate | Pre-existing |
| F7 | Addon redundancy audit | Pre-existing |
| F8 | Frigate followups (face recognition tuning, LPR, GenAI, PTZ password rotation) | Pre-existing |

---

## 📝 Append-only event log (Melbourne local time)

- **2026-04-09 ~08:00** — Started v4.0.0rc1 deploy. Backed up v3.2.1 to `/config/custom_components/z2m_irrigation.v3.2.1.bak.…` (mistake — dotted dir inside `custom_components/` broke HA loader). rsync'd v4.0 source. First restart attempt failed with `ModuleNotFoundError: custom_components.z2m_irrigation.v3`.
- **2026-04-09 ~08:20** — Diagnosed: HA loader misread the dotted backup dir name as a `v3` submodule. Moved backup to `/config/z2m_irrigation_backups/`. Saved gotcha to memory.
- **2026-04-09 ~08:23** — Restart succeeded. v4.0.0rc1 loaded clean — 43 entities, schedule engine started, calculator running with neutral defaults.
- **2026-04-09 ~08:24** — Real-world: Back Garden + Lilly Pilly valves reported `water_shortage`. Logged as R1/R2.
- **2026-04-09 ~08:41** — User accidentally overwrote `/config/.storage/lovelace.dashboard_new`.
- **2026-04-09 ~08:55** — Restored dashboard from encrypted Apr 8 backup (`46fab5af`, password `XSH2-DSQ0-…`). 268 KB, 7 views, 66 cards.
- **2026-04-09 ~09:00** — User walked through Configure flow (steps 1/2/3). VPD entity selected was hPa-native (Ecowitt). Calculator over-watering at 172.8 L.
- **2026-04-09 ~09:05** — Built rc-2 with unit-aware conversion in `weather.py`. Local math validation: 172.8 L → 108.0 L exactly. Pushed to GitHub `feat/v4.0`. rsynced to HA. Restarted.
- **2026-04-09 ~09:15** — rc-2 verified live: `today_calculation = 108.03 L`, dryness 1.163, vpd 0.938 kPa. Math matches expected exactly.
- **2026-04-09 ~09:25** — Started D1/D2/D3 dashboard fixes. D1 (Hero card null guards) deployed and verified clean by user console output. D2/D3 attempted with auto-entities patches but errors persisted on user's hard refresh. Pivoted to hardcoding the 4 known valves into the dashboard YAML to bypass auto-entities entirely. Replaced ALL 4 auto-entities instances. Deployed. Errors confirmed gone.
- **2026-04-09 ~09:50** — User created a "Test" schedule via the JS editor card. Schedule appears in the list but with `last_outcome: skipped_no_zones`. Hero card on Today tab shows "No schedule yet" even though the schedule exists. Investigated.
- **2026-04-09 ~09:55** — Found B2: schedule editor JS card stored zone identifier as the slugified entity_id (`lilly_pilly`) instead of the friendly_name (`Lilly Pilly`). Engine looked up `lilly_pilly` in `mgr.valves` (which has `Lilly Pilly` as key), found nothing, returned zero zones, stamped `skipped_no_zones`.
- **2026-04-09 ~09:58** — Fixed B2 in `_discoverZones()` (use `friendly_name` for zone id). Synced editor card to HA. Repaired user's existing Test schedule via `z2m_irrigation.update_schedule` setting `zones=['Lilly Pilly']`.
- **2026-04-09 ~10:00** — Found D4: dashboard YAML referenced `sensor.z2m_irrigation_next_run_summary` but actual entity_id is `sensor.z2m_irrigation_next_run` (HA generates entity_id from friendly_name, not unique_id). Same for `_active_session_summary` → `_active_session`. 13 broken refs. sed-fixed all of them. Deployed dashboard. Restarted HA.
- **2026-04-09 ~10:00** — User asked about per-zone factor adjustment ("can I tell it I want more water in a certain zone?") and sunrise-45m schedule timing. Both logged as F-A (per-zone editor) and F-B (sun-relative schedules) in the feature gaps section.
