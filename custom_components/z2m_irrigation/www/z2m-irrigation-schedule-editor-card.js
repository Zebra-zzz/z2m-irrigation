/*
 * z2m-irrigation-schedule-editor-card
 *
 * v4.0-rc-1 — in-dashboard schedule editor for the z2m_irrigation
 * integration. A self-contained vanilla custom Lovelace card with a
 * real form: name + time + days + mode + zones + (optional) fixed
 * liters + enabled. On submit it calls
 * `z2m_irrigation.create_schedule` and refreshes its own state.
 *
 * Replaces the "use Developer Tools" prompt that the dashboard
 * shipped on the Schedule tab in alpha-5. No helpers required —
 * the card maintains its form state in component-local memory.
 *
 * Usage:
 *
 *   type: custom:z2m-irrigation-schedule-editor-card
 *
 * Optional config keys:
 *
 *   default_mode: smart           # default for the mode select
 *   default_time: "06:00"         # default for the time input
 *   compact: false                # tighter padding for sidebar use
 *
 * The card auto-discovers all valves by scanning hass.states for
 * entities with `entity_id` matching switch.* under the
 * z2m_irrigation domain (filtered by attribute set), so the zone
 * checkboxes are always in sync with what the integration has
 * actually discovered.
 *
 * Like the embed card, this file ships under the integration's
 * www/ directory and is auto-registered as a frontend resource by
 * `__init__.py._register_frontend_once`. No manual Lovelace
 * resource entry required.
 */

const CARD_VERSION = "4.0.0rc1";
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const MODES = [
  { value: "smart", label: "Smart (calculator)" },
  { value: "fixed", label: "Fixed liters per zone" },
];

class Z2MIrrigationScheduleEditorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = {};
    this._form = null;       // current form state (in-memory)
    this._zonesCache = null; // memoised zone list discovered from hass
    this._submitting = false;
    this._lastError = null;
    this._lastSuccess = null;
    this._rendered = false;
  }

  setConfig(config) {
    this._config = {
      default_mode: "smart",
      default_time: "06:00",
      compact: false,
      ...config,
    };
    this._resetForm();
    this._render();
  }

  set hass(hass) {
    const firstHass = !this._hass;
    this._hass = hass;
    // Refresh discovered zones whenever the entity registry changes.
    // Cheap — just iterates hass.states once and bails if unchanged.
    const zones = this._discoverZones();
    const zonesChanged = JSON.stringify(zones) !== JSON.stringify(this._zonesCache);
    if (zonesChanged) {
      this._zonesCache = zones;
      this._render();
    } else if (firstHass) {
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return this._config.compact ? 5 : 7;
  }

  static getStubConfig() {
    return {};
  }

  // ───────────────────────────────────────────────────────────────────
  // State
  // ───────────────────────────────────────────────────────────────────

  _resetForm() {
    this._form = {
      name: "",
      time: this._config.default_time || "06:00",
      days: [],                   // [] = every day
      mode: this._config.default_mode || "smart",
      zones: [],                  // [] in smart = all in_smart_cycle
      fixed_liters_per_zone: "",
      enabled: true,
    };
    this._lastError = null;
    this._lastSuccess = null;
  }

  _discoverZones() {
    if (!this._hass || !this._hass.states) return [];
    const out = [];
    for (const [eid, st] of Object.entries(this._hass.states)) {
      // Heuristic: switch entities whose underlying valve has a
      // matching `_zone_factor` sensor are integration valves.
      // The integration always registers both, so the existence of
      // the zone_factor sensor is a reliable filter that doesn't
      // depend on the entity registry's `integration` field.
      if (!eid.startsWith("switch.")) continue;
      if (eid === "switch.z2m_irrigation_master_enable") continue;
      const base = eid.replace("switch.", "");
      if (this._hass.states[`sensor.${base}_zone_factor`]) {
        out.push({
          id: base,
          name: (st.attributes && st.attributes.friendly_name) || base,
        });
      }
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  }

  // ───────────────────────────────────────────────────────────────────
  // Rendering
  // ───────────────────────────────────────────────────────────────────

  _render() {
    if (!this._form) return;

    if (!this._rendered) {
      this.shadowRoot.appendChild(this._buildStyle());
      this._root = document.createElement("div");
      this._root.className = "z2m-edit";
      this.shadowRoot.appendChild(this._root);
      this._rendered = true;
    }

    this._root.dataset.compact = this._config.compact ? "1" : "0";
    this._root.innerHTML = this._buildBody();
    this._wireEvents();
  }

  _buildStyle() {
    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; }
      .z2m-edit {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
        -webkit-font-smoothing: antialiased;
        background: var(--ha-card-background, var(--card-background-color, #fff));
        color: var(--primary-text-color, #1d1d1f);
        border-radius: 18px;
        padding: 24px 26px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.02);
        border: 1px solid rgba(127,127,127,0.10);
      }
      .z2m-edit[data-compact="1"] { padding: 16px 18px; }

      .accent {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        opacity: 0.55;
        margin-bottom: 8px;
      }
      .title {
        font-size: 22px;
        font-weight: 600;
        line-height: 1.2;
        letter-spacing: -0.01em;
        margin-bottom: 18px;
      }
      .z2m-edit[data-compact="1"] .title { font-size: 17px; margin-bottom: 12px; }

      .field {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin-bottom: 14px;
      }
      .field label {
        font-size: 12px;
        font-weight: 600;
        opacity: 0.7;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .field input[type="text"],
      .field input[type="time"],
      .field input[type="number"],
      .field select {
        font: inherit;
        font-size: 15px;
        padding: 10px 12px;
        background: rgba(127,127,127,0.08);
        color: inherit;
        border: 1px solid rgba(127,127,127,0.20);
        border-radius: 10px;
        outline: none;
        transition: border-color 200ms ease, background 200ms ease;
      }
      .field input:focus,
      .field select:focus {
        border-color: #0d7377;
        background: rgba(13,115,119,0.05);
      }

      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .chip {
        font-size: 12px;
        font-weight: 600;
        padding: 7px 14px;
        border-radius: 18px;
        background: rgba(127,127,127,0.10);
        color: inherit;
        border: 1px solid rgba(127,127,127,0.16);
        cursor: pointer;
        user-select: none;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        transition: all 150ms ease;
      }
      .chip:hover {
        background: rgba(127,127,127,0.16);
      }
      .chip[data-on="1"] {
        background: #0d7377;
        color: #fff;
        border-color: #0d7377;
      }

      .row {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
      }
      .row input[type="checkbox"] {
        accent-color: #0d7377;
        width: 16px;
        height: 16px;
        cursor: pointer;
      }

      .actions {
        display: flex;
        gap: 10px;
        margin-top: 22px;
      }
      .btn {
        flex: 1;
        font: inherit;
        font-size: 14px;
        font-weight: 600;
        padding: 12px 18px;
        border-radius: 12px;
        border: 1px solid rgba(127,127,127,0.20);
        background: rgba(127,127,127,0.08);
        color: inherit;
        cursor: pointer;
        transition: all 200ms ease;
      }
      .btn:hover { background: rgba(127,127,127,0.14); }
      .btn-primary {
        background: #0d7377;
        color: #fff;
        border-color: #0d7377;
      }
      .btn-primary:hover { background: #0a5d61; }
      .btn[disabled] { opacity: 0.5; cursor: not-allowed; }

      .feedback {
        margin-top: 14px;
        padding: 10px 14px;
        border-radius: 10px;
        font-size: 13px;
        line-height: 1.4;
      }
      .feedback.error {
        background: rgba(192,57,43,0.08);
        color: #c0392b;
        border: 1px solid rgba(192,57,43,0.22);
      }
      .feedback.success {
        background: rgba(13,115,119,0.08);
        color: #0d7377;
        border: 1px solid rgba(13,115,119,0.22);
      }

      .hint {
        font-size: 12px;
        opacity: 0.6;
        margin-top: -8px;
        margin-bottom: 14px;
      }

      .field.hidden { display: none; }
    `;
    return style;
  }

  _buildBody() {
    const f = this._form;
    const zones = this._zonesCache || [];

    const dayChips = DAYS.map(d => `
      <span class="chip" data-day="${d}" data-on="${f.days.includes(d) ? 1 : 0}">
        ${d}
      </span>
    `).join("");

    const zoneChips = zones.length === 0
      ? `<span class="hint">No zones discovered yet. Wait for the integration to find your valves.</span>`
      : zones.map(z => `
        <span class="chip" data-zone="${this._escape(z.id)}" data-on="${f.zones.includes(z.id) ? 1 : 0}">
          ${this._escape(z.name)}
        </span>
      `).join("");

    const fixedHidden = f.mode === "smart" ? " hidden" : "";

    return `
      <div class="accent">create schedule</div>
      <div class="title">New irrigation schedule</div>

      <div class="field">
        <label>Name</label>
        <input type="text" id="f-name" placeholder="e.g. Morning smart" value="${this._escape(f.name)}">
      </div>

      <div class="field">
        <label>Time (local)</label>
        <input type="time" id="f-time" value="${this._escape(f.time)}">
      </div>

      <div class="field">
        <label>Days</label>
        <div class="chips" id="f-days">${dayChips}</div>
      </div>
      <div class="hint">Tap to select. Empty = every day.</div>

      <div class="field">
        <label>Mode</label>
        <select id="f-mode">
          ${MODES.map(m => `
            <option value="${m.value}"${f.mode === m.value ? " selected" : ""}>${m.label}</option>
          `).join("")}
        </select>
      </div>

      <div class="field">
        <label>Zones</label>
        <div class="chips" id="f-zones">${zoneChips}</div>
      </div>
      <div class="hint">
        Tap to select. Empty + smart mode = all zones marked
        <em>in smart cycle</em>.
      </div>

      <div class="field${fixedHidden}" id="f-fixed-wrap">
        <label>Fixed liters per zone</label>
        <input type="number" id="f-fixed" min="0" max="1000" step="0.5"
               placeholder="e.g. 25"
               value="${this._escape(f.fixed_liters_per_zone)}">
      </div>

      <div class="row">
        <input type="checkbox" id="f-enabled" ${f.enabled ? "checked" : ""}>
        <label for="f-enabled">Enabled</label>
      </div>

      <div class="actions">
        <button type="button" class="btn" id="f-reset">Reset</button>
        <button type="button" class="btn btn-primary" id="f-submit"
                ${this._submitting ? "disabled" : ""}>
          ${this._submitting ? "Creating…" : "Create schedule"}
        </button>
      </div>

      ${this._lastError ? `<div class="feedback error">${this._escape(this._lastError)}</div>` : ""}
      ${this._lastSuccess ? `<div class="feedback success">${this._escape(this._lastSuccess)}</div>` : ""}
    `;
  }

  _wireEvents() {
    if (!this._root) return;

    const root = this._root;
    const f = this._form;

    const $name = root.querySelector("#f-name");
    if ($name) $name.addEventListener("input", e => { f.name = e.target.value; });

    const $time = root.querySelector("#f-time");
    if ($time) $time.addEventListener("input", e => { f.time = e.target.value; });

    const $mode = root.querySelector("#f-mode");
    if ($mode) $mode.addEventListener("change", e => {
      f.mode = e.target.value;
      this._render();
    });

    const $fixed = root.querySelector("#f-fixed");
    if ($fixed) $fixed.addEventListener("input", e => { f.fixed_liters_per_zone = e.target.value; });

    const $enabled = root.querySelector("#f-enabled");
    if ($enabled) $enabled.addEventListener("change", e => { f.enabled = e.target.checked; });

    // Day chips toggle
    root.querySelectorAll("#f-days .chip").forEach(el => {
      el.addEventListener("click", () => {
        const day = el.dataset.day;
        const idx = f.days.indexOf(day);
        if (idx >= 0) f.days.splice(idx, 1);
        else f.days.push(day);
        el.dataset.on = idx >= 0 ? "0" : "1";
      });
    });

    // Zone chips toggle
    root.querySelectorAll("#f-zones .chip").forEach(el => {
      el.addEventListener("click", () => {
        const zone = el.dataset.zone;
        const idx = f.zones.indexOf(zone);
        if (idx >= 0) f.zones.splice(idx, 1);
        else f.zones.push(zone);
        el.dataset.on = idx >= 0 ? "0" : "1";
      });
    });

    // Reset button
    const $reset = root.querySelector("#f-reset");
    if ($reset) $reset.addEventListener("click", () => {
      this._resetForm();
      this._render();
    });

    // Submit button
    const $submit = root.querySelector("#f-submit");
    if ($submit) $submit.addEventListener("click", () => this._submit());
  }

  // ───────────────────────────────────────────────────────────────────
  // Submit
  // ───────────────────────────────────────────────────────────────────

  async _submit() {
    if (this._submitting) return;
    if (!this._hass) return;

    const f = this._form;

    // Client-side validation
    if (!f.name || !f.name.trim()) {
      this._lastError = "Name is required.";
      this._lastSuccess = null;
      this._render();
      return;
    }
    if (!/^\d{1,2}:\d{2}$/.test(f.time)) {
      this._lastError = "Time must be HH:MM.";
      this._lastSuccess = null;
      this._render();
      return;
    }
    if (f.mode === "fixed") {
      const liters = parseFloat(f.fixed_liters_per_zone);
      if (!liters || liters <= 0) {
        this._lastError = "Fixed mode requires a positive liters-per-zone value.";
        this._lastSuccess = null;
        this._render();
        return;
      }
      if (f.zones.length === 0) {
        this._lastError = "Fixed mode requires at least one zone.";
        this._lastSuccess = null;
        this._render();
        return;
      }
    }

    const data = {
      name: f.name.trim(),
      time: f.time,
      days: f.days.slice(),
      mode: f.mode,
      zones: f.zones.slice(),
      enabled: !!f.enabled,
    };
    if (f.mode === "fixed") {
      data.fixed_liters_per_zone = parseFloat(f.fixed_liters_per_zone);
    }

    this._submitting = true;
    this._lastError = null;
    this._lastSuccess = null;
    this._render();

    try {
      await this._hass.callService("z2m_irrigation", "create_schedule", data);
      this._lastSuccess = `Created "${data.name}". The Schedule list refreshes within a few seconds.`;
      this._resetFormPreservingSuccess();
    } catch (e) {
      this._lastError = (e && e.message) ? e.message : String(e);
    } finally {
      this._submitting = false;
      this._render();
    }
  }

  _resetFormPreservingSuccess() {
    const success = this._lastSuccess;
    this._resetForm();
    this._lastSuccess = success;
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

if (!customElements.get("z2m-irrigation-schedule-editor-card")) {
  customElements.define(
    "z2m-irrigation-schedule-editor-card",
    Z2MIrrigationScheduleEditorCard
  );
}

window.customCards = window.customCards || [];
if (!window.customCards.find(c => c.type === "z2m-irrigation-schedule-editor-card")) {
  window.customCards.push({
    type: "z2m-irrigation-schedule-editor-card",
    name: "Z2M Irrigation schedule editor",
    description: "In-dashboard form for creating z2m_irrigation schedules",
    preview: false,
    documentationURL: "https://github.com/Zebra-zzz/z2m-irrigation",
  });
}

console.info(
  `%c z2m-irrigation-schedule-editor-card %c v${CARD_VERSION} `,
  "background: #0d7377; color: white; font-weight: 700; padding: 2px 4px; border-radius: 3px 0 0 3px;",
  "background: #2c3e50; color: white; padding: 2px 4px; border-radius: 0 3px 3px 0;"
);
