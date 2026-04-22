# Z2M Irrigation (Sonoff Valves)

A full irrigation stack for Home Assistant built around Sonoff SWV Zigbee
valves exposed via Zigbee2MQTT. Local-first, no cloud services.

## What it does

- Auto-discovers Sonoff SWV valves over MQTT
- VPD-driven calculator computes per-zone litre targets from weather + rain
- Local scheduler with fixed and sun-relative times (sunrise/sunset ±N min)
- Single-valve-at-a-time queue runner with 5-second inter-zone gap
- Multi-layer safety: hardware quantitative close + software overshoot,
  stuck-flow, MQTT-silence, and panic guardrails
- Bundled dashboard (Hero / Setup / Schedule / Log / Trends tabs) and two
  custom Lovelace cards
- SQLite session history (90-day retention) + JSON config store, both in HA
  backups

## Quick start

1. Install via HACS, restart Home Assistant
2. Settings → Devices & Services → **Add Integration** → *Z2M Irrigation*
3. Deploy the bundled dashboard from `dashboards/z2m_irrigation.yaml`
4. Open the Setup tab, tune `factor` / `l_per_mm` / `base_mm` per zone
5. Open the Schedule tab, add a schedule, enrol zones into smart mode

## Requirements

- Home Assistant 2024.1.0+
- MQTT integration configured
- Zigbee2MQTT with Sonoff SWV valves paired
- A weather integration exposing VPD and daily rain

## Documentation

Full documentation: [https://github.com/Zebra-zzz/z2m-irrigation](https://github.com/Zebra-zzz/z2m-irrigation)
