# Z2M Irrigation (Sonoff Valves)

Home Assistant custom integration that pairs with Zigbee2MQTT to control and monitor **Sonoff SWV** water valves.

## Features
- Auto-discovery from Zigbee2MQTT (`bridge/devices`)
- Per-valve entities:
  - `switch` – Valve on/off
  - `sensor` **Flow** (L/min)
  - `sensor` **Session Used** (L)
  - `sensor` **Total** (L, total_increasing)
  - `sensor` **Total Minutes** (min, total_increasing)
- Services:
  - `z2m_irrigation.start_timed` (`valve`, `minutes`)
  - `z2m_irrigation.start_liters` (`valve`, `liters`)
  - `z2m_irrigation.reset_totals` (optional `valve`)

> Use the Zigbee2MQTT **friendly_name** (the MQTT leaf topic) for the `valve` field, e.g. `Water Valve 3`.

## Install (HACS)
1. HACS → **Integrations** → 3-dots → **Custom repositories**
2. Add `https://github.com/Zebra-zzz/z2m-irrigation` as **Integration**
3. Install, then **Restart Home Assistant**
4. Settings → Devices & Services → **Add Integration** → *Z2M Irrigation (Sonoff Valves)*

## Options
- **MQTT base topic** (default `zigbee2mqtt`)

## Notes
- Flow-based liters are integrated from `flow` reports published by Zigbee2MQTT on `zigbee2mqtt/<friendly_name>`.
