# Z2M Irrigation — v4.0 dashboard

A pre-built Lovelace dashboard for the `z2m_irrigation` custom integration.
Wires every entity exposed by alpha-1 through alpha-4 into a 4-tab UI:

| Tab | Purpose |
| --- | --- |
| **Today** | Hero status card, calculator card, per-zone live tiles, manual run sliders |
| **Schedule** | Stored schedule list with per-row run-now / enable-disable, queue, next run |
| **Setup** | Master enable, panic clear, per-zone config rows, integration option links |
| **Insight** | 30-day stacked bar, per-zone leaderboard, per-zone trend charts, schedule timeline, avg flow strip |

## Required HACS frontend cards

Install these via HACS → Frontend before importing the dashboard. Most are
common; you may already have several from other dashboards.

| Card | HACS name |
| --- | --- |
| `button-card` | [custom-cards/button-card](https://github.com/custom-cards/button-card) |
| `mushroom` | [piitaya/lovelace-mushroom](https://github.com/piitaya/lovelace-mushroom) |
| `auto-entities` | [thomasloven/lovelace-auto-entities](https://github.com/thomasloven/lovelace-auto-entities) |
| `apexcharts-card` | [RomRider/apexcharts-card](https://github.com/RomRider/apexcharts-card) |
| `mini-graph-card` | [kalkih/mini-graph-card](https://github.com/kalkih/mini-graph-card) |
| `stack-in-card` | [custom-cards/stack-in-card](https://github.com/custom-cards/stack-in-card) |
| `card-mod` | [thomasloven/lovelace-card-mod](https://github.com/thomasloven/lovelace-card-mod) |
| `layout-card` | [thomasloven/lovelace-layout-card](https://github.com/thomasloven/lovelace-layout-card) |

After installing each card, restart Home Assistant once so the resources
are picked up.

## Installation

The dashboard is shipped as a single self-contained YAML file. Two import
paths — pick whichever you prefer.

### Path A — UI import (recommended)

1. Open **Settings → Dashboards → Add Dashboard → New dashboard from scratch**
2. Give it a title (e.g. "Irrigation"), pick an icon (`mdi:sprinkler`), click **Create**
3. Open the new dashboard, click the **⋮** menu top-right → **Edit dashboard**
4. Click the **⋮** menu again → **Raw configuration editor**
5. Copy-paste the entire contents of [`z2m_irrigation.yaml`](z2m_irrigation.yaml)
   over whatever's in there
6. Click **Save**, then close the editor

### Path B — Storage mode

If your `configuration.yaml` already has `lovelace: { mode: storage }` and
you want this dashboard added at the YAML layer, place the file at
`/config/dashboards/z2m_irrigation.yaml` and add to `configuration.yaml`:

```yaml
lovelace:
  mode: storage
  dashboards:
    z2m-irrigation:
      mode: yaml
      filename: dashboards/z2m_irrigation.yaml
      title: Irrigation
      icon: mdi:sprinkler
      show_in_sidebar: true
```

Restart Home Assistant. The dashboard appears in the sidebar.

## First-time check

After import, walk through each tab:

1. **Today** — the Hero card should show one of:
   - "No schedule yet" (fresh install)
   - "Next run …" (you've created a schedule)
   - "Running …" (a session is in flight)
   - "Paused" (master enable is off)
   - "🚨 Kill the water pump" (panic state — investigate immediately)
2. **Schedule** — should be empty until you create one. Use Developer
   Tools → Services → `z2m_irrigation.create_schedule` to add the first.
3. **Setup** — the Per-zone config section should auto-populate with one
   row per discovered Sonoff valve.
4. **Insight** — the 30-day chart will be empty on a brand-new install
   and fills in over the first week of use.

## Customization

The dashboard uses `button-card` templates defined at the top of the YAML
file. To re-theme:

- **`z2m_base`** — base typography and palette. Edit `font-family`,
  `border-radius`, padding, and the box-shadow for global look.
- **`z2m_hero`** — the big status card. The 5-state visual logic lives
  in the `custom_fields.accent` template; the per-state CSS is in `style`.
- **`z2m_zone_tile`** — per-zone tile on the Today tab. Adjust grid
  layout, font sizes, or the `custom_fields.metric` template to show a
  different number (e.g. weekly total instead of last-run).

The default accent color is teal (`#0d7377`); to change it dashboard-wide,
search-replace that hex code.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Hero card is blank | One of the required entities (`binary_sensor.z2m_irrigation_panic` etc.) is missing. Verify the integration has loaded successfully and that you're on v4.0.0a1 or newer. |
| "No history yet" on every zone tile | No completed sessions yet — run a manual cycle once and the per-zone last-run sensors will populate. |
| Per-zone tiles don't appear | `auto-entities` couldn't find any switches with `integration: z2m_irrigation`. Check that the integration discovered your valves (Settings → Devices & Services → Z2M Irrigation should list them). |
| Insight 30-day chart is empty after a week of use | The aggregator cache hasn't refreshed yet. Run `z2m_irrigation.recalculate_now` and reload the dashboard, or wait for the next 15-min refresh tick. |
| Calculator card says "hasn't run yet" | No valves discovered yet, or the calculator hasn't been refreshed. Wait a moment after HA startup, then call `z2m_irrigation.recalculate_now`. |
| Schedule list rows show but tap-to-run does nothing | Verify the schedule passes the gates (master enable on, no panic, no skip-today). Check Settings → System → Logs for the engine's skip reason. |

## Embed card (alpha-6+)

A standalone custom Lovelace card ships alongside the integration so
**any other dashboard** can drop a compact "is irrigation running right
now?" indicator with one line of YAML — no `button-card` / `mushroom`
dependency needed in the target dashboard.

The integration auto-registers the JS resource on setup, so you don't
need to add anything under Settings → Dashboards → Resources. After
the integration loads, the card type is immediately available
everywhere:

```yaml
type: custom:z2m-irrigation-embed-card
```

Optional config keys:

```yaml
type: custom:z2m-irrigation-embed-card
compact: true                       # smaller single-row variant
title: Garden                       # override the default "Irrigation"
navigation_path: /irrigation/today  # tap target — default no navigation
```

Five visual states resolved automatically from integration entities:

| State | Trigger entity | Visual |
| --- | --- | --- |
| 🚨 panic | `binary_sensor.z2m_irrigation_panic` == on | Red accent + reason + affected valves |
| 🔵 running | `binary_sensor.z2m_irrigation_any_running` == on | Teal accent + valve name + live progress bar + flow + ETA |
| ⚪ paused | `switch.z2m_irrigation_master_enable` == off | Grey + "Toggle Master Enable to resume" |
| 🔵 scheduled | `sensor.z2m_irrigation_next_run_summary` set | Teal + next run time + schedule name + zone count + estimate |
| ⚪ idle | fallback | Grey + "No schedule yet" |

In compact mode the card collapses to a single row (still shows the
state, title, sub-line, and a thin progress bar in running state) so
it fits in a column or sidebar dashboard alongside other compact cards.

## What's still pending in v4.0

- **rc-1** — polish, an in-dashboard schedule editor (replacing the
  current "use Developer Tools" prompt), and the demolition guide for
  legacy v3.x helpers and template sensors.
