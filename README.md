# Z2M Irrigation (Sonoff Valves)

Home Assistant custom integration for **Sonoff SWV** valves via **Zigbee2MQTT**.

## Entities per valve
- **Valve** (switch)
- **Flow** (L/min)
- **Session Used** (L)
- **Total** (L, total_increasing)
- **Total Minutes** (min, total_increasing)
- **Session Remaining** (min; only when a timed run is active)

## Services
- `z2m_irrigation.start_timed` — `valve`, `minutes`
- `z2m_irrigation.start_liters` — `valve`, `liters`
- `z2m_irrigation.reset_totals` — optional `valve`
- `z2m_irrigation.rescan` — re-requests device list

Use the Zigbee2MQTT **friendly name** (e.g. `Water Valve 3`) for `valve`.

## Options (gear icon)
- **MQTT base topic** (default `zigbee2mqtt`)
- **Manual valves** (one friendly name per line) – optional fallback if discovery fails.
- **Flow scale** multiplier (default `1.0`). Incoming device `flow` is multiplied by this to produce **L/min**.
  - If your device reports **m³/min**, set `flow_scale = 1000`.
  - If it reports **L/h**, set `flow_scale = 1/60 ≈ 0.0166667`.

## How discovery works
The integration subscribes to:
- `${base}/bridge/devices`
- `${base}/bridge/config/devices`

and requests the list via `${base}/bridge/config/devices/get`. It then subscribes to `${base}/<friendly_name>` for each SWV valve.

