/*
 * z2m-irrigation-embed-card
 *
 * v4.0-alpha-6 — a small custom Lovelace card so any dashboard can drop
 * a compact "is irrigation happening right now?" indicator without
 * pulling in button-card / mushroom / auto-entities. Three visual
 * variants resolved automatically from the integration's entities:
 *
 *   panic     — binary_sensor.z2m_irrigation_panic == on
 *   running   — binary_sensor.z2m_irrigation_any_running == on
 *   paused    — switch.z2m_irrigation_master_enable == off
 *   scheduled — sensor.z2m_irrigation_next_run_summary != no_schedule
 *   idle      — fallback
 *
 * Usage in any Lovelace dashboard:
 *
 *   type: custom:z2m-irrigation-embed-card
 *   compact: false                     # optional, default false
 *   title: Irrigation                  # optional override
 *   navigation_path: /irrigation/today # optional, tap target
 *
 * The integration auto-registers this file via add_extra_js_url so the
 * card is available in every dashboard immediately after the integration
 * loads — no manual Lovelace resource entry required.
 *
 * The card is intentionally framework-free: no Lit, no React, just a
 * vanilla custom element with a shadow DOM. Stays under ~400 lines and
 * has no build step.
 */

const CARD_VERSION = "4.0.0a6";

// ─────────────────────────────────────────────────────────────────────────────
// State resolver — pure function over hass.states
// ─────────────────────────────────────────────────────────────────────────────

const STATE_PANIC = "panic";
const STATE_RUNNING = "running";
const STATE_PAUSED = "paused";
const STATE_SCHEDULED = "scheduled";
const STATE_IDLE = "idle";

function resolveState(hass) {
  if (!hass || !hass.states) return STATE_IDLE;
  const get = (id) => hass.states[id];
  const panic = get("binary_sensor.z2m_irrigation_panic");
  const running = get("binary_sensor.z2m_irrigation_any_running");
  const master = get("switch.z2m_irrigation_master_enable");
  const next = get("sensor.z2m_irrigation_next_run_summary");

  if (panic && panic.state === "on") return STATE_PANIC;
  if (running && running.state === "on") return STATE_RUNNING;
  if (master && master.state === "off") return STATE_PAUSED;
  if (next && next.state !== "no_schedule" && next.state !== "unknown") {
    return STATE_SCHEDULED;
  }
  return STATE_IDLE;
}

// Format an ISO timestamp into a friendly relative or absolute display.
// Returns "" if the input isn't parseable.
function formatNextRun(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const opts = { weekday: "long", hour: "2-digit", minute: "2-digit" };
  return d.toLocaleString(undefined, opts);
}

function formatElapsed(seconds) {
  if (seconds == null || isNaN(seconds)) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

// ─────────────────────────────────────────────────────────────────────────────
// The custom element
// ─────────────────────────────────────────────────────────────────────────────

class Z2MIrrigationEmbedCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._lastState = null;
    this._renderRoot = null;
  }

  // Lovelace contract
  setConfig(config) {
    this._config = {
      compact: false,
      title: "Irrigation",
      navigation_path: null,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  // Lovelace size hint — used by view layout. Compact = 1 grid row,
  // full = 2 rows.
  getCardSize() {
    return this._config.compact ? 1 : 2;
  }

  static getConfigElement() {
    return null;
  }

  static getStubConfig() {
    return { compact: false };
  }

  // ───────────────────────────────────────────────────────────────────
  // Rendering
  // ───────────────────────────────────────────────────────────────────

  _render() {
    if (!this._hass) return;
    const state = resolveState(this._hass);

    // Cheap re-render guard: bail out if nothing this card cares about
    // has changed since last render. Saves a few cycles on dashboards
    // that re-push hass on every state event.
    const fingerprint = this._fingerprint(state);
    if (fingerprint === this._lastState) return;
    this._lastState = fingerprint;

    if (!this._renderRoot) {
      this._renderRoot = document.createElement("div");
      this._renderRoot.classList.add("z2m-card");
      this._renderRoot.addEventListener("click", () => this._onClick());
      this.shadowRoot.appendChild(this._buildStyle());
      this.shadowRoot.appendChild(this._renderRoot);
    }

    this._renderRoot.dataset.state = state;
    this._renderRoot.dataset.compact = this._config.compact ? "1" : "0";
    this._renderRoot.innerHTML = this._buildBody(state);
  }

  _fingerprint(state) {
    // Include the live numbers that the running state shows so the
    // card actually updates as a session progresses.
    const get = (id) => this._hass.states[id];
    const active = get("sensor.z2m_irrigation_active_session_summary");
    const next = get("sensor.z2m_irrigation_next_run_summary");
    const panic = get("binary_sensor.z2m_irrigation_panic");
    const liters = active && active.attributes ? active.attributes.session_liters : null;
    const flow = active && active.attributes ? active.attributes.flow_lpm : null;
    return [
      state,
      this._config.compact,
      active ? active.state : "",
      liters,
      flow,
      next ? next.state : "",
      panic ? panic.state : "",
    ].join("|");
  }

  _onClick() {
    if (!this._config.navigation_path) return;
    history.pushState(null, "", this._config.navigation_path);
    window.dispatchEvent(new Event("location-changed", { composed: true }));
  }

  _buildStyle() {
    const style = document.createElement("style");
    style.textContent = `
      :host {
        display: block;
      }
      .z2m-card {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
        -webkit-font-smoothing: antialiased;
        background: var(--ha-card-background, var(--card-background-color, #fff));
        color: var(--primary-text-color, #1d1d1f);
        border-radius: 18px;
        padding: 20px 22px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.02);
        border: 1px solid rgba(127,127,127,0.10);
        position: relative;
        overflow: hidden;
        cursor: default;
        transition: transform 200ms ease, box-shadow 200ms ease;
      }
      .z2m-card[data-clickable="1"] { cursor: pointer; }
      .z2m-card[data-clickable="1"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 6px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.03);
      }
      .z2m-card::before {
        content: "";
        position: absolute;
        left: 0;
        top: 0;
        width: 4px;
        height: 100%;
        background: var(--accent);
      }
      .z2m-card[data-state="panic"]     { --accent: #c0392b; background: linear-gradient(0deg, rgba(192,57,43,0.06), rgba(192,57,43,0.02)); }
      .z2m-card[data-state="running"]   { --accent: #0d7377; }
      .z2m-card[data-state="scheduled"] { --accent: #0d7377; }
      .z2m-card[data-state="paused"]    { --accent: #888; }
      .z2m-card[data-state="idle"]      { --accent: #888; }

      .accent {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        opacity: 0.55;
        margin-bottom: 6px;
      }
      .title {
        font-size: 22px;
        font-weight: 600;
        line-height: 1.2;
        letter-spacing: -0.01em;
      }
      .sub {
        font-size: 13px;
        opacity: 0.7;
        margin-top: 6px;
        line-height: 1.4;
      }

      /* Live progress bar for running state */
      .progress-track {
        margin-top: 14px;
        height: 6px;
        background: rgba(127,127,127,0.18);
        border-radius: 3px;
        overflow: hidden;
      }
      .progress-fill {
        height: 100%;
        background: var(--accent);
        border-radius: 3px;
        transition: width 400ms ease;
      }
      .running-numbers {
        margin-top: 10px;
        display: flex;
        gap: 18px;
        font-size: 12px;
        opacity: 0.8;
      }
      .running-numbers > span > b { font-weight: 600; opacity: 1; }

      /* Compact mode — single row */
      .z2m-card[data-compact="1"] {
        padding: 14px 18px;
      }
      .z2m-card[data-compact="1"] .accent { display: none; }
      .z2m-card[data-compact="1"] .title { font-size: 15px; }
      .z2m-card[data-compact="1"] .sub { font-size: 12px; margin-top: 2px; }
      .z2m-card[data-compact="1"] .progress-track { margin-top: 8px; height: 4px; }
      .z2m-card[data-compact="1"] .running-numbers { display: none; }
    `;
    return style;
  }

  _buildBody(state) {
    if (!this._hass) return "";
    if (this._config.navigation_path) {
      // Set the data attribute via property since innerHTML wipes it.
      // We re-set after the innerHTML write below.
    }

    const builder = {
      panic: () => this._buildPanic(),
      running: () => this._buildRunning(),
      paused: () => this._buildPaused(),
      scheduled: () => this._buildScheduled(),
      idle: () => this._buildIdle(),
    }[state] || this._buildIdle.bind(this);

    const body = builder();

    // Toggle clickable styling — set after innerHTML is written via the
    // dataset (the style hook reads data-clickable).
    queueMicrotask(() => {
      if (this._renderRoot && this._config.navigation_path) {
        this._renderRoot.dataset.clickable = "1";
      } else if (this._renderRoot) {
        this._renderRoot.dataset.clickable = "0";
      }
    });

    return body;
  }

  // ───────────────────────────────────────────────────────────────────
  // State variant builders
  // ───────────────────────────────────────────────────────────────────

  _buildPanic() {
    const panic = this._hass.states["binary_sensor.z2m_irrigation_panic"];
    const reason = panic && panic.attributes ? (panic.attributes.reason || "unknown") : "unknown";
    const affected = panic && panic.attributes ? (panic.attributes.affected_valves || []) : [];
    return `
      <div class="accent">⚠ panic</div>
      <div class="title">🚨 Kill the water pump</div>
      <div class="sub">
        Reason: <b>${this._escape(reason)}</b><br>
        ${affected.length ? "Affected: " + affected.map(v => this._escape(v)).join(", ") : "Manual investigation required."}
      </div>
    `;
  }

  _buildRunning() {
    const active = this._hass.states["sensor.z2m_irrigation_active_session_summary"];
    if (!active || !active.attributes) {
      return `
        <div class="accent">running</div>
        <div class="title">${this._escape(this._config.title)} is running</div>
      `;
    }
    const a = active.attributes;
    const name = a.name || active.state || "a zone";
    const liters = a.session_liters != null ? a.session_liters.toFixed(1) : "—";
    const target = a.target_liters != null ? a.target_liters.toFixed(0) : null;
    const flow = a.flow_lpm != null ? a.flow_lpm.toFixed(2) : "—";
    const elapsed = a.elapsed_seconds != null ? formatElapsed(a.elapsed_seconds) : "";
    const eta = a.eta_seconds != null ? formatElapsed(a.eta_seconds) : null;

    let pct = 0;
    if (a.target_liters && a.session_liters != null && a.target_liters > 0) {
      pct = Math.min(100, Math.max(0, (a.session_liters / a.target_liters) * 100));
    }
    const progressBar = a.target_liters
      ? `<div class="progress-track"><div class="progress-fill" style="width:${pct.toFixed(1)}%"></div></div>`
      : "";

    return `
      <div class="accent">running</div>
      <div class="title">${this._escape(name)}</div>
      <div class="sub">${liters} L${target ? " / " + target + " L" : ""} · ${flow} L/min</div>
      ${progressBar}
      <div class="running-numbers">
        ${elapsed ? `<span>elapsed <b>${elapsed}</b></span>` : ""}
        ${eta ? `<span>eta <b>${eta}</b></span>` : ""}
      </div>
    `;
  }

  _buildPaused() {
    return `
      <div class="accent">paused</div>
      <div class="title">${this._escape(this._config.title)} paused</div>
      <div class="sub">Toggle <b>Master Enable</b> to resume scheduled runs.</div>
    `;
  }

  _buildScheduled() {
    const next = this._hass.states["sensor.z2m_irrigation_next_run_summary"];
    if (!next || !next.attributes) return this._buildIdle();
    const a = next.attributes;
    const formattedNext = formatNextRun(a.next_run_at) || formatNextRun(next.state);
    const liters = a.estimated_total_liters != null ? a.estimated_total_liters.toFixed(1) + " L" : null;
    const zones = (a.zones || []).length;
    const subParts = [];
    if (a.schedule_name) subParts.push(this._escape(a.schedule_name));
    if (zones) subParts.push(`${zones} zone${zones === 1 ? "" : "s"}`);
    if (liters) subParts.push(`~${liters}`);
    if (a.skip_today) subParts.unshift("⏭ skipped today");

    return `
      <div class="accent">next run</div>
      <div class="title">${this._escape(formattedNext || "Scheduled")}</div>
      <div class="sub">${subParts.join(" · ") || "Scheduled"}</div>
    `;
  }

  _buildIdle() {
    return `
      <div class="accent">idle</div>
      <div class="title">${this._escape(this._config.title)}</div>
      <div class="sub">No schedule yet. Create one on the Schedule tab.</div>
    `;
  }

  _escape(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Register
// ─────────────────────────────────────────────────────────────────────────────

if (!customElements.get("z2m-irrigation-embed-card")) {
  customElements.define("z2m-irrigation-embed-card", Z2MIrrigationEmbedCard);
}

// Lovelace card-picker registration. Both old and new style — the
// integration ships against multiple HA frontend versions and the
// picker reads whichever it finds.
window.customCards = window.customCards || [];
if (!window.customCards.find(c => c.type === "z2m-irrigation-embed-card")) {
  window.customCards.push({
    type: "z2m-irrigation-embed-card",
    name: "Z2M Irrigation embed",
    description: "Compact running indicator for the z2m_irrigation integration",
    preview: false,
    documentationURL: "https://github.com/Zebra-zzz/z2m-irrigation",
  });
}

console.info(
  `%c z2m-irrigation-embed-card %c v${CARD_VERSION} `,
  "background: #0d7377; color: white; font-weight: 700; padding: 2px 4px; border-radius: 3px 0 0 3px;",
  "background: #2c3e50; color: white; padding: 2px 4px; border-radius: 0 3px 3px 0;"
);
