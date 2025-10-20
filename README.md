# Z2M Irrigation (Sonoff Valves)

Custom integration for Home Assistant that pairs with **Zigbee2MQTT** to control and monitor **Sonoff SWV** water valves.

## What you get
- Auto-discovery from Zigbee2MQTT (works with `bridge/devices` and `bridge/config/devices`)
- Entities per valve:
  - **Valve** (switch)
  - **Flow** (L/min)
  - **Session Used** (L) – liters this run
  - **Total** (L, total_increasing)
  - **Total Minutes** (min, total_increasing)
- Services:
  - `z2m_irrigation.start_timed` → fields: `valve`, `minutes`
  - `z2m_irrigation.start_liters` → fields: `valve`, `liters`
  - `z2m_irrigation.reset_totals` → field: optional `valve`

> Use the Zigbee2MQTT **friendly_name** (e.g. `Water Valve 3`) for the `valve` field.

## Install (HACS)
1. HACS → *Integrations* → ⋯ → **Custom repositories**
2. Add `https://github.com/Zebra-zzz/z2m-irrigation` as **Integration**
3. Install the integration, then **Restart Home Assistant**
4. Settings → *Devices & Services* → **Add Integration** → *Z2M Irrigation (Sonoff Valves)*

## Options
- **MQTT base topic** (default `zigbee2mqtt`)

## Notes
- Flow and session totals are integrated from the `flow` and `state` messages published by Zigbee2MQTT on `zigbee2mqtt/<friendly_name>`.
- Timed runs use HA timers and send `.../<friendly_name>/set` with `{"state":"ON"/"OFF"}`.

