# Z2M Irrigation (Sonoff Valves)

Home Assistant custom integration for **Sonoff SWV** valves via **Zigbee2MQTT**.

## Entities per valve
- **Valve** (switch)
- **Flow** (L/min)
- **Session Used** (L)
- **Total** (L, total_increasing)
- **Total Minutes** (min, total_increasing)

## Services
- `z2m_irrigation.start_timed` — `valve`, `minutes`
- `z2m_irrigation.start_liters` — `valve`, `liters`
- `z2m_irrigation.reset_totals` — optional `valve`
- `z2m_irrigation.rescan` — re-requests device list

Use the Zigbee2MQTT **friendly name** (e.g. `Water Valve 3`) for `valve`.

## Install (HACS)
1. HACS → *Integrations* → ⋯ → **Custom repositories** → add `https://github.com/Zebra-zzz/z2m-irrigation` as **Integration**.
2. Install → **Restart Home Assistant**.
3. Settings → *Devices & Services* → **Add Integration** → *Z2M Irrigation (Sonoff Valves)*.

## Options (gear icon)
- **MQTT base topic** (default `zigbee2mqtt`)
- **Manual valves** (one friendly name per line) – optional fallback if discovery fails.

## How discovery works
The integration subscribes to:
- `${base}/bridge/devices`
- `${base}/bridge/config/devices`

and requests the list via `${base}/bridge/config/devices/get`. It then subscribes to `${base}/<friendly_name>` for each SWV valve.

