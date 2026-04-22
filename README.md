# Z2M Irrigation (Sonoff Valves)

A full irrigation stack for Home Assistant built around Sonoff SWV Zigbee valves
exposed via Zigbee2MQTT. Includes a VPD-driven calculator, a local scheduler
with sun-relative times, a single-valve-at-a-time queue runner, multi-layer
safety guardrails, per-zone trend charts, and a self-contained dashboard with
two bundled custom Lovelace cards.

Local-first. No cloud services, no external databases.

## Status

- Current version: **4.1.1** (see [CHANGELOG.md](CHANGELOG.md))
- Minimum Home Assistant: **2024.1.0**
- Tested on HA OS with MQTT + Zigbee2MQTT addons, 4 Sonoff SWV valves

## What you get

**Integration** (`custom_components/z2m_irrigation/`)

- Auto-discovers Sonoff SWV valves from MQTT and creates a device per valve
- Per-valve sensors: flow rate, session volume, session duration, 24h/7d
  usage, zone config (factor / l_per_mm / base_mm), last-run summary, daily
  history (90-day rolling)
- Global sensors: calculator output (per-zone litre targets), next-run
  summary, week summary, schedule history, session log, daily totals
- Binary sensors: any-valve-running, panic, per-valve in-smart-cycle
- Services: `start_timed`, `start_liters`, `run_smart_now`, `create_schedule`,
  `update_schedule`, `delete_schedule`, `set_zone_factor`, `set_zone_l_per_mm`,
  `set_zone_base_mm`, `set_zone_in_smart_cycle`, `skip_today`,
  `clear_skip_today`, `reset_totals`, `rescan`

**Dashboard** (`dashboards/z2m_irrigation.yaml`)

- Hero tile (running / scheduled / idle state)
- Per-zone tiles with last-run + 24h/7d usage + in-smart-cycle toggle
- Setup tab: editable per-zone factor / l_per_mm / base_mm + plant demand
  reference table
- Schedule tab: custom editor card (create / edit / delete, fixed or
  sun-relative times, smart or per-zone fixed-liters modes)
- Log tab: 200-entry session log (target vs software-computed volume, flow
  rate, trigger type, OK/panic flag)
- Trends tab: 7-day per-zone volume charts

**Custom Lovelace cards** (`custom_components/z2m_irrigation/www/`)

- `z2m-irrigation-embed-card` — compact running / scheduled / idle tile
- `z2m-irrigation-schedule-editor-card` — full schedule editor

## How the calculator works

For each zone enrolled in smart mode:

```
dryness  = clamp(0.85 + vpd_kpa / 3, 0.8, 1.5)
need_mm  = max(0, base_mm * dryness - rain_today - 0.7 * forecast_24h_mm)
liters   = need_mm * zone_factor * zone_l_per_mm
```

- `vpd_kpa` is the 24-hour rolling average of VPD read from your weather
  sensor (Ecowitt hPa or native kPa — the adapter normalises)
- `rain_today` and `forecast_24h_mm` come from your weather provider
- `base_mm` is the per-zone "what a healthy week would want per day" target
- `zone_factor` lets you bias a zone up or down without touching base_mm
- `zone_l_per_mm` is the zone's area calibration (litres to deliver one mm of
  depth across the zone's footprint)

The scheduler fires at a schedule's time, collects currently-enrolled zones,
hands their target litres to the queue runner, and waters one zone at a time
with a 5-second inter-zone gap. The Sonoff SWV's hardware
`cyclic_quantitative_irrigation` counter is what actually closes each valve at
target — the integration's software-side flow integration is telemetry only.

## Safety layers

1. Device hardware quantitative counter (primary close, ~2.5% accurate)
2. Software 140% overshoot guardrail (force-off at 1.4× target)
3. Software stuck-flow guardrail (force-off after 10 min of no litre progress)
4. Software MQTT-silence guardrail (force-off after 5 min with no state publish)
5. Panic system (fires `EVENT_PANIC_REQUIRED` + persistent notification +
   optional `kill_switch_entity` pump cut)

## Install

### Via HACS (recommended)

1. HACS → Integrations → three-dot menu → **Custom repositories**
2. Add `https://github.com/Zebra-zzz/z2m-irrigation` as an Integration
3. Find *Z2M Irrigation (Sonoff Valves)* in HACS, download, restart Home Assistant
4. Settings → Devices & Services → **Add Integration** → search *Z2M Irrigation*

### Manual

1. Download the latest release from the [releases page](https://github.com/Zebra-zzz/z2m-irrigation/releases)
2. Extract `custom_components/z2m_irrigation/` into `/config/custom_components/`
3. Restart Home Assistant, then add the integration as above

## Dashboard install

The dashboard lives in [dashboards/z2m_irrigation.yaml](dashboards/z2m_irrigation.yaml).
See [dashboards/README.md](dashboards/README.md) for the install steps
(storage-mode deploy + browser hard-refresh).

## Requirements

- Home Assistant 2024.1.0+
- MQTT integration configured
- Zigbee2MQTT running with Sonoff SWV valves paired
- A weather integration that exposes VPD and daily-rain sensors (Ecowitt,
  native HA weather forecast, or similar)

## Data and persistence

- **SQLite**: `/config/z2m_irrigation.db` — session history, append-mostly
  time-series of every valve run. 90-day retention, 200 rows on the dashboard.
- **JSON store**: `/config/.storage/z2m_irrigation.<entry_id>` — mutable zone
  config, schedules, daily summary cache, VPD 24h rolling buffer.
- Both are included in standard HA backups.

## Troubleshooting

**Valves not discovered** — confirm Z2M is publishing to
`zigbee2mqtt/<friendly_name>` and that the integration's MQTT base topic
matches (default `zigbee2mqtt`, editable in the integration options).

**Calculator output is zero / unknown** — check that your VPD sensor reports a
numeric state and that the weather adapter is reading it. Logs show
`weather: sensor.<name> <value> <unit> → <kPa>` at DEBUG when a sample comes
through.

**Session delivered less than target** — expected on valves whose hardware
flow counter disagrees with the software flow integration. The device's
quantitative counter is the authoritative stop signal. The dashboard's
*Software computed* column is telemetry, not truth.

**Session shows 0 L and cut off after ~10 min** — the stuck-flow guardrail
fired. Usually means no water was actually reaching the valve (empty tank,
pump not primed, closed upstream valve).

**VPD buffer empty after restart** — as of v4.1.1 the hydration path is fixed
and logs `VPD buffer hydrated: N loaded, M pruned` on startup. If you still
see zero loaded, check that `/config/.storage/z2m_irrigation.<entry_id>` has a
`vpd_buffer` key under `data`.

For anything else, open an issue with your HA version, integration version,
logs filtered for `z2m_irrigation`, and a brief description of what you
expected vs observed.

## Links

- [CHANGELOG.md](CHANGELOG.md) — full version history
- [dashboards/README.md](dashboards/README.md) — dashboard install
- [Issues](https://github.com/Zebra-zzz/z2m-irrigation/issues)

## License

MIT — see [LICENSE](LICENSE).
