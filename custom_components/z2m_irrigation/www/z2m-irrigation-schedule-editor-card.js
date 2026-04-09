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

const CARD_VERSION = "4.0.0rc3";
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const MODES = [
  { value: "smart", label: "Smart (calculator)" },
  { value: "fixed", label: "Fixed litres per zone" },
];

// v4.0-rc-3 (F-B UX): all 6 sun events HA's sun integration provides.
// User picks one from a dropdown; we serialise back to the canonical
// `event±N` string the backend understands.
const SUN_EVENTS = [
  { value: "sunrise",  label: "🌅 Sunrise" },
  { value: "sunset",   label: "🌇 Sunset" },
  { value: "dawn",     label: "🌄 Dawn (civil twilight start)" },
  { value: "dusk",     label: "🌆 Dusk (civil twilight end)" },
  { value: "noon",     label: "☀️ Solar noon" },
  { value: "midnight", label: "🌙 Solar midnight" },
];

// Parse a time string into a UI form representation:
//   { type: 'fixed',  fixed_time: '06:00' }
//   { type: 'sun',    sun_event: 'sunrise', sun_direction: 'before', sun_minutes: 45 }
function parseTimeString(s) {
  if (!s) return { type: "fixed", fixed_time: "06:00", sun_event: "sunrise", sun_direction: "after", sun_minutes: 0 };
  const trimmed = s.trim().toLowerCase();
  // Fixed HH:MM
  if (/^\d{1,2}:\d{2}$/.test(trimmed)) {
    return { type: "fixed", fixed_time: s, sun_event: "sunrise", sun_direction: "after", sun_minutes: 0 };
  }
  // Sun-relative
  const m = trimmed.match(/^(sunrise|sunset|dawn|dusk|noon|midnight)\s*([+-]?\s*\d+)?\s*m?$/);
  if (m) {
    const event = m[1];
    const offsetRaw = (m[2] || "0").replace(/\s+/g, "");
    const offset = parseInt(offsetRaw, 10) || 0;
    return {
      type: "sun",
      fixed_time: "06:00",
      sun_event: event,
      sun_direction: offset < 0 ? "before" : "after",
      sun_minutes: Math.abs(offset),
    };
  }
  // Fallback: treat as fixed
  return { type: "fixed", fixed_time: s, sun_event: "sunrise", sun_direction: "after", sun_minutes: 0 };
}

// Inverse: serialise the UI form representation to the canonical string
// the backend `_TIME_RE` schema expects.
function serializeTimeString(f) {
  if (f.type === "fixed") {
    return f.fixed_time || "06:00";
  }
  // sun
  const event = f.sun_event || "sunrise";
  const minutes = parseInt(f.sun_minutes, 10) || 0;
  if (minutes === 0) return event;
  const sign = (f.sun_direction === "before") ? "-" : "+";
  return `${event}${sign}${minutes}`;
}

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
    const prevSchedules = this._schedulesCache;
    this._hass = hass;

    // Refresh discovered zones whenever the entity registry changes.
    // Cheap — just iterates hass.states once and bails if unchanged.
    const zones = this._discoverZones();
    const zonesChanged = JSON.stringify(zones) !== JSON.stringify(this._zonesCache);

    // v4.0-rc-3 (F-J): also re-render when the existing schedules list
    // changes (after a CREATE / UPDATE / DELETE service call lands).
    const schedules = this._existingSchedules();
    this._schedulesCache = schedules;
    const schedulesChanged = JSON.stringify(schedules) !== JSON.stringify(prevSchedules);

    if (zonesChanged) {
      this._zonesCache = zones;
      this._render();
    } else if (schedulesChanged) {
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
    const initialTime = this._config.default_time || "06:00";
    const parsed = parseTimeString(initialTime);
    this._form = {
      // v4.0-rc-3 (F-J): editing_id is null in CREATE mode and set to a
      // schedule_id string in EDIT mode. Submit routes to either
      // create_schedule or update_schedule based on this flag.
      editing_id: null,
      name: "",
      // v4.0-rc-3 hotfix iter 3 (F-B UX): time is now derived from
      // four UI fields. The submit handler serialises them via
      // serializeTimeString() into the canonical backend format.
      time_type: parsed.type,           // "fixed" | "sun"
      fixed_time: parsed.fixed_time,    // "HH:MM"
      sun_event: parsed.sun_event,      // sunrise|sunset|dawn|dusk|noon|midnight
      sun_direction: parsed.sun_direction, // "before" | "after"
      sun_minutes: parsed.sun_minutes,  // integer
      days: [],                   // [] = every day
      mode: this._config.default_mode || "smart",
      zones: [],                  // [] in smart = all in_smart_cycle
      fixed_liters_per_zone: "",
      enabled: true,
    };
    this._lastError = null;
    this._lastSuccess = null;
  }

  // v4.0-rc-3 (F-J) — read existing schedules from the integration's
  // global Schedules sensor. Returns an array of schedule dicts as
  // stored by zone_store, or [] if the sensor isn't loaded yet.
  _existingSchedules() {
    if (!this._hass || !this._hass.states) return [];
    const s = this._hass.states["sensor.z2m_irrigation_schedules"];
    if (!s || !s.attributes) return [];
    return s.attributes.schedules || [];
  }

  // v4.0-rc-3 (F-J) — pull a stored schedule into the form for editing.
  _loadScheduleForEdit(schedule_id) {
    const sched = this._existingSchedules().find(s => s.id === schedule_id);
    if (!sched) {
      this._lastError = `Schedule ${schedule_id} not found in the sensor cache.`;
      this._render();
      return;
    }
    const parsed = parseTimeString(sched.time || "06:00");
    this._form = {
      editing_id: sched.id,
      name: sched.name || "",
      time_type: parsed.type,
      fixed_time: parsed.fixed_time,
      sun_event: parsed.sun_event,
      sun_direction: parsed.sun_direction,
      sun_minutes: parsed.sun_minutes,
      days: Array.isArray(sched.days) ? sched.days.slice() : [],
      mode: sched.mode || "smart",
      zones: Array.isArray(sched.zones) ? sched.zones.slice() : [],
      fixed_liters_per_zone:
        sched.fixed_liters_per_zone != null
          ? String(sched.fixed_liters_per_zone)
          : "",
      enabled: sched.enabled !== false,
    };
    this._lastError = null;
    this._lastSuccess = null;
    this._render();
  }

  async _deleteSchedule(schedule_id, name) {
    if (!this._hass) return;
    const ok = window.confirm(
      `Delete schedule "${name || schedule_id}"?\n\nThis cannot be undone.`,
    );
    if (!ok) return;
    try {
      await this._hass.callService(
        "z2m_irrigation", "delete_schedule",
        { schedule_id },
      );
      this._lastSuccess = `Deleted "${name || schedule_id}".`;
      // If we were editing the deleted schedule, reset to create mode.
      if (this._form && this._form.editing_id === schedule_id) {
        this._resetForm();
      }
      this._render();
    } catch (e) {
      this._lastError = (e && e.message) ? e.message : String(e);
      this._render();
    }
  }

  _discoverZones() {
    if (!this._hass || !this._hass.states) return [];
    // v4.0-rc-3 hotfix iteration 2 — enumerate by `sensor.*_zone_factor`
    // directly. Previous heuristic walked switch entities and looked
    // for a parallel `sensor.<base>_zone_factor`, but the user has
    // BOTH `switch.<zone>` (z2m-exposed) AND `switch.<zone>_valve`
    // (this integration's) for some zones, while others (like Front
    // Garden) only have `switch.<zone>_valve`. The previous heuristic
    // mis-handled the `_valve` suffix and silently dropped zones that
    // only had the integration's switch — Front Garden disappeared
    // from the editor's zone chips.
    //
    // Enumerating by `sensor.*_zone_factor` is bulletproof: every
    // valve discovered by the integration registers exactly one of
    // these sensors via _ensure_valve. The friendly_name on the
    // sensor is "<Zone Name> Zone Factor"; we strip the suffix to
    // recover the bare zone name (which IS the valve.friendly_name
    // and the engine's lookup key — see B2 fix earlier in rc-3).
    const out = [];
    const seen = new Set();
    for (const [eid, st] of Object.entries(this._hass.states)) {
      if (!eid.startsWith("sensor.")) continue;
      if (!eid.endsWith("_zone_factor")) continue;
      // Skip the integration's own zone factor entities for zones we
      // already added (just in case of dupes from a stale config entry).
      const fullName = (st.attributes && st.attributes.friendly_name) || eid;
      // Friendly name is "<Zone Name> Zone Factor" — strip the suffix.
      const cleaned = fullName.replace(/\s*Zone Factor$/i, "").trim();
      if (!cleaned) continue;
      if (seen.has(cleaned)) continue;
      seen.add(cleaned);
      out.push({
        id: cleaned,
        name: cleaned,
      });
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
      .hint.hidden { display: none; }

      /* v4.0-rc-3 (F-B UX) — sun event offset row */
      .sun-offset-row {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }
      .sun-offset-row select {
        flex: 0 0 auto;
        min-width: 100px;
      }
      .sun-offset-row input[type="number"] {
        flex: 0 0 90px;
        text-align: right;
      }
      .sun-offset-suffix {
        font-size: 14px;
        opacity: 0.7;
      }

      /* v4.0-rc-3 (F-J) — existing schedule list */
      .title.small { font-size: 16px; margin-bottom: 12px; }
      .divider {
        border: none;
        border-top: 1px solid rgba(127,127,127,0.18);
        margin: 22px 0 18px 0;
      }
      .sched-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-bottom: 6px;
      }
      .sched-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 12px 14px;
        background: rgba(127,127,127,0.06);
        border: 1px solid rgba(127,127,127,0.12);
        border-radius: 12px;
        transition: all 200ms ease;
      }
      .sched-row:hover {
        background: rgba(127,127,127,0.10);
      }
      .sched-row.editing {
        background: rgba(13,115,119,0.08);
        border-color: rgba(13,115,119,0.40);
      }
      .sched-info { flex: 1; min-width: 0; }
      .sched-name {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 3px;
      }
      .sched-meta {
        font-size: 11px;
        opacity: 0.65;
        line-height: 1.4;
      }
      .sched-actions {
        display: flex;
        gap: 6px;
        flex-shrink: 0;
      }
      .btn-mini {
        font: inherit;
        font-size: 11px;
        font-weight: 600;
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid rgba(127,127,127,0.20);
        background: var(--ha-card-background, #fff);
        color: inherit;
        cursor: pointer;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        transition: all 150ms ease;
      }
      .btn-mini:hover { background: rgba(127,127,127,0.10); }
      .btn-mini.btn-edit:hover { background: rgba(13,115,119,0.12); border-color: #0d7377; }
      .btn-mini.btn-delete:hover { background: rgba(192,57,43,0.12); border-color: #c0392b; color: #c0392b; }

      .badge {
        display: inline-block;
        font-size: 9px;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 10px;
        margin-left: 6px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        vertical-align: middle;
      }
      .badge-on  { background: rgba(13,115,119,0.15); color: #0d7377; }
      .badge-off { background: rgba(127,127,127,0.18); color: rgba(127,127,127,0.85); }
    `;
    return style;
  }

  _buildBody() {
    const f = this._form;
    const zones = this._zonesCache || [];
    const isEdit = !!f.editing_id;

    // v4.0-rc-3 (F-J) — existing schedule list at the top with
    // Edit and Delete buttons per row.
    const existing = this._existingSchedules();
    const existingList = existing.length === 0
      ? `<div class="hint">No schedules yet. Use the form below to create your first one.</div>`
      : existing.map(s => {
          const days = (s.days && s.days.length) ? s.days.join(",") : "every day";
          const zoneCount = (s.zones || []).length;
          const enabledBadge = s.enabled === false
            ? '<span class="badge badge-off">disabled</span>'
            : '<span class="badge badge-on">enabled</span>';
          const isThisOne = isEdit && f.editing_id === s.id;
          return `
            <div class="sched-row${isThisOne ? ' editing' : ''}">
              <div class="sched-info">
                <div class="sched-name">${this._escape(s.name || s.id)} ${enabledBadge}</div>
                <div class="sched-meta">
                  ${this._escape(s.time || '?')} ·
                  ${this._escape(days)} ·
                  ${this._escape(s.mode || 'smart')} ·
                  ${zoneCount} zone${zoneCount === 1 ? '' : 's'}
                  ${s.last_run_outcome ? ' · last: ' + this._escape(s.last_run_outcome) : ''}
                </div>
              </div>
              <div class="sched-actions">
                <button type="button" class="btn-mini btn-edit"
                        data-edit-id="${this._escape(s.id)}">edit</button>
                <button type="button" class="btn-mini btn-delete"
                        data-delete-id="${this._escape(s.id)}"
                        data-delete-name="${this._escape(s.name || s.id)}">delete</button>
              </div>
            </div>
          `;
        }).join("");

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
      <div class="accent">existing schedules</div>
      <div class="title small">${existing.length} schedule${existing.length === 1 ? '' : 's'}</div>
      <div class="sched-list">${existingList}</div>
      <hr class="divider">

      <div class="accent">${isEdit ? 'edit schedule' : 'create schedule'}</div>
      <div class="title">
        ${isEdit ? 'Editing: ' + this._escape(f.name || f.editing_id) : 'New irrigation schedule'}
      </div>

      <div class="field">
        <label>Name</label>
        <input type="text" id="f-name" placeholder="e.g. Morning smart" value="${this._escape(f.name)}">
      </div>

      <div class="field">
        <label>Time mode</label>
        <select id="f-time-type">
          <option value="fixed"${f.time_type === 'fixed' ? ' selected' : ''}>⏰ Fixed time</option>
          <option value="sun"${f.time_type === 'sun' ? ' selected' : ''}>☀️ Sun event</option>
        </select>
      </div>

      <div class="field${f.time_type === 'fixed' ? '' : ' hidden'}" id="f-fixed-time-wrap">
        <label>Time (local, 24-hour)</label>
        <input type="time" id="f-fixed-time" value="${this._escape(f.fixed_time)}">
      </div>

      <div class="field${f.time_type === 'sun' ? '' : ' hidden'}" id="f-sun-event-wrap">
        <label>Sun event</label>
        <select id="f-sun-event">
          ${SUN_EVENTS.map(e => `
            <option value="${e.value}"${f.sun_event === e.value ? ' selected' : ''}>${e.label}</option>
          `).join('')}
        </select>
      </div>

      <div class="field${f.time_type === 'sun' ? '' : ' hidden'}" id="f-sun-offset-wrap">
        <label>Offset</label>
        <div class="sun-offset-row">
          <select id="f-sun-direction">
            <option value="before"${f.sun_direction === 'before' ? ' selected' : ''}>Before</option>
            <option value="after"${f.sun_direction === 'after' ? ' selected' : ''}>After</option>
          </select>
          <input type="number" id="f-sun-minutes" min="0" max="180" step="1"
                 value="${this._escape(String(f.sun_minutes ?? 0))}">
          <span class="sun-offset-suffix">minutes</span>
        </div>
      </div>
      <div class="hint${f.time_type === 'sun' ? '' : ' hidden'}" id="f-sun-hint">
        Will fire <strong>${f.sun_minutes || 0} min ${f.sun_direction || 'after'} ${f.sun_event || 'sunrise'}</strong>
        — computed from your HA system location (Settings → System →
        General → Location).
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
        <button type="button" class="btn" id="f-reset">
          ${isEdit ? 'Cancel edit' : 'Reset form'}
        </button>
        <button type="button" class="btn btn-primary" id="f-submit"
                ${this._submitting ? "disabled" : ""}>
          ${this._submitting
              ? (isEdit ? 'Saving…' : 'Creating…')
              : (isEdit ? 'Save changes' : 'Create schedule')}
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

    // v4.0-rc-3 (F-B UX) — time mode + sun event dropdowns
    const $timeType = root.querySelector("#f-time-type");
    if ($timeType) $timeType.addEventListener("change", e => {
      f.time_type = e.target.value;
      this._render();
    });
    const $fixedTime = root.querySelector("#f-fixed-time");
    if ($fixedTime) $fixedTime.addEventListener("input", e => { f.fixed_time = e.target.value; });

    const $sunEvent = root.querySelector("#f-sun-event");
    if ($sunEvent) $sunEvent.addEventListener("change", e => {
      f.sun_event = e.target.value;
      this._render(); // re-render so the hint text updates
    });
    const $sunDir = root.querySelector("#f-sun-direction");
    if ($sunDir) $sunDir.addEventListener("change", e => {
      f.sun_direction = e.target.value;
      this._render();
    });
    const $sunMin = root.querySelector("#f-sun-minutes");
    if ($sunMin) $sunMin.addEventListener("input", e => {
      f.sun_minutes = parseInt(e.target.value, 10) || 0;
      this._render();
    });

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

    // Reset / cancel-edit button
    const $reset = root.querySelector("#f-reset");
    if ($reset) $reset.addEventListener("click", () => {
      this._resetForm();
      this._render();
    });

    // Submit button
    const $submit = root.querySelector("#f-submit");
    if ($submit) $submit.addEventListener("click", () => this._submit());

    // v4.0-rc-3 (F-J) — existing schedule list edit + delete buttons
    root.querySelectorAll(".btn-edit").forEach(el => {
      el.addEventListener("click", () => {
        const id = el.dataset.editId;
        if (id) this._loadScheduleForEdit(id);
      });
    });
    root.querySelectorAll(".btn-delete").forEach(el => {
      el.addEventListener("click", () => {
        const id = el.dataset.deleteId;
        const name = el.dataset.deleteName;
        if (id) this._deleteSchedule(id, name);
      });
    });
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
    // v4.0-rc-3 hotfix iter 3 (F-B UX): serialise the dropdown form
    // fields into the canonical backend string. The serializer always
    // produces a valid format because the dropdowns are constrained
    // to known values.
    const timeStr = serializeTimeString(f);
    if (f.time_type === "fixed") {
      if (!/^\d{1,2}:\d{2}$/.test(timeStr)) {
        this._lastError = "Pick a valid fixed time.";
        this._lastSuccess = null;
        this._render();
        return;
      }
    } else {
      const minutes = parseInt(f.sun_minutes, 10);
      if (isNaN(minutes) || minutes < 0 || minutes > 180) {
        this._lastError = "Sun-event offset must be 0–180 minutes.";
        this._lastSuccess = null;
        this._render();
        return;
      }
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

    const isEdit = !!f.editing_id;
    const data = {
      name: f.name.trim(),
      time: timeStr,
      days: f.days.slice(),
      mode: f.mode,
      zones: f.zones.slice(),
      enabled: !!f.enabled,
    };
    if (f.mode === "fixed") {
      data.fixed_liters_per_zone = parseFloat(f.fixed_liters_per_zone);
    } else {
      // v4.0-rc-3 (F-J): explicit null when switching back to smart
      // mode during an edit, so we clear any leftover fixed value.
      data.fixed_liters_per_zone = null;
    }

    this._submitting = true;
    this._lastError = null;
    this._lastSuccess = null;
    this._render();

    try {
      if (isEdit) {
        // EDIT mode — call update_schedule with the existing id.
        await this._hass.callService(
          "z2m_irrigation", "update_schedule",
          { schedule_id: f.editing_id, ...data },
        );
        this._lastSuccess = `Saved changes to "${data.name}".`;
      } else {
        // CREATE mode — call create_schedule.
        await this._hass.callService(
          "z2m_irrigation", "create_schedule", data,
        );
        this._lastSuccess = `Created "${data.name}". The Schedule list refreshes within a few seconds.`;
      }
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
