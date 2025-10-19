import { html, LitElement, css } from "https://unpkg.com/lit@2.7.5?module";

class IrrigationSessionsPanel extends LitElement {
  static properties = {
    hass: { type: Object },
    sessions: { type: Array },
    loading: { type: Boolean },
    filterValve: { type: String },
    filterStartDate: { type: String },
    filterEndDate: { type: String },
    sortColumn: { type: String },
    sortDirection: { type: String },
  };

  constructor() {
    super();
    this.sessions = [];
    this.loading = true;
    this.filterValve = "";
    this.filterStartDate = "";
    this.filterEndDate = "";
    this.sortColumn = "start";
    this.sortDirection = "desc";
  }

  async firstUpdated() {
    await this.loadSessions();
  }

  async loadSessions() {
    this.loading = true;
    try {
      const result = await this.hass.callWS({
        type: "z2m_irrigation/sessions/list",
        valve_filter: this.filterValve || undefined,
        start_date: this.filterStartDate || undefined,
        end_date: this.filterEndDate || undefined,
      });
      this.sessions = result.sessions || [];
    } catch (error) {
      console.error("Failed to load sessions:", error);
      this.sessions = [];
    }
    this.loading = false;
  }

  async deleteSession(sessionId) {
    if (!confirm("Delete this session?")) return;

    try {
      await this.hass.callWS({
        type: "z2m_irrigation/sessions/delete",
        session_id: sessionId,
      });
      await this.loadSessions();
    } catch (error) {
      console.error("Failed to delete session:", error);
      alert("Failed to delete session");
    }
  }

  async clearAllSessions() {
    if (!confirm("Clear ALL sessions? This cannot be undone!")) return;

    try {
      await this.hass.callWS({
        type: "z2m_irrigation/sessions/clear",
      });
      await this.loadSessions();
    } catch (error) {
      console.error("Failed to clear sessions:", error);
      alert("Failed to clear sessions");
    }
  }

  exportCSV() {
    const headers = [
      "Valve",
      "Start",
      "End",
      "Duration (min)",
      "Litres",
      "Avg L/min",
      "Mode",
      "Target",
      "Ended By",
      "Notes",
    ];

    const rows = this.sortedSessions.map((s) => [
      s.valve,
      s.start,
      s.end,
      s.duration_min,
      s.litres,
      s.avg_lpm,
      s.mode,
      JSON.stringify(s.target),
      s.ended_by,
      s.notes,
    ]);

    const csv = [headers, ...rows].map((row) => row.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `irrigation_sessions_${new Date().toISOString()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  sortBy(column) {
    if (this.sortColumn === column) {
      this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
    } else {
      this.sortColumn = column;
      this.sortDirection = "asc";
    }
  }

  get sortedSessions() {
    const sorted = [...this.sessions].sort((a, b) => {
      let aVal = a[this.sortColumn];
      let bVal = b[this.sortColumn];

      if (typeof aVal === "string") {
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
      }

      if (aVal < bVal) return this.sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return this.sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return sorted;
  }

  formatDateTime(isoString) {
    return new Date(isoString).toLocaleString();
  }

  formatTarget(target) {
    if (!target) return "-";
    if (target.minutes) return `${target.minutes} min`;
    if (target.litres) return `${target.litres} L`;
    return "-";
  }

  render() {
    return html`
      <div class="container">
        <div class="header">
          <h1>💧 Irrigation Sessions</h1>
          <div class="actions">
            <button @click="${this.exportCSV}" ?disabled="${!this.sessions.length}">
              Export CSV
            </button>
            <button
              @click="${this.clearAllSessions}"
              class="danger"
              ?disabled="${!this.sessions.length}"
            >
              Clear All
            </button>
          </div>
        </div>

        <div class="filters">
          <input
            type="text"
            placeholder="Filter by valve..."
            .value="${this.filterValve}"
            @input="${(e) => {
              this.filterValve = e.target.value;
              this.loadSessions();
            }}"
          />
          <input
            type="date"
            .value="${this.filterStartDate}"
            @input="${(e) => {
              this.filterStartDate = e.target.value;
              this.loadSessions();
            }}"
          />
          <input
            type="date"
            .value="${this.filterEndDate}"
            @input="${(e) => {
              this.filterEndDate = e.target.value;
              this.loadSessions();
            }}"
          />
          <button @click="${() => {
            this.filterValve = "";
            this.filterStartDate = "";
            this.filterEndDate = "";
            this.loadSessions();
          }}">
            Clear Filters
          </button>
        </div>

        ${
          this.loading
            ? html`<div class="loading">Loading sessions...</div>`
            : this.sessions.length === 0
            ? html`<div class="empty">No sessions found</div>`
            : html`
                <div class="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th @click="${() => this.sortBy("valve")}">
                          Valve ${this.sortColumn === "valve" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("start")}">
                          Start ${this.sortColumn === "start" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("end")}">
                          End ${this.sortColumn === "end" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("duration_min")}">
                          Duration (min) ${this.sortColumn === "duration_min" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("litres")}">
                          Litres ${this.sortColumn === "litres" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("avg_lpm")}">
                          Avg L/min ${this.sortColumn === "avg_lpm" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th @click="${() => this.sortBy("mode")}">
                          Mode ${this.sortColumn === "mode" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th>Target</th>
                        <th @click="${() => this.sortBy("ended_by")}">
                          Ended By ${this.sortColumn === "ended_by" ? (this.sortDirection === "asc" ? "▲" : "▼") : ""}
                        </th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${this.sortedSessions.map(
                        (session) => html`
                          <tr>
                            <td>${session.valve}</td>
                            <td>${this.formatDateTime(session.start)}</td>
                            <td>${this.formatDateTime(session.end)}</td>
                            <td>${session.duration_min}</td>
                            <td>${session.litres}</td>
                            <td>${session.avg_lpm}</td>
                            <td>${session.mode}</td>
                            <td>${this.formatTarget(session.target)}</td>
                            <td>${session.ended_by}</td>
                            <td>
                              <button
                                class="delete-btn"
                                @click="${() => this.deleteSession(session.id)}"
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        `
                      )}
                    </tbody>
                  </table>
                </div>
              `
        }
      </div>
    `;
  }

  static styles = css`
    :host {
      display: block;
      padding: 16px;
      font-family: var(--paper-font-body1_-_font-family);
    }

    .container {
      max-width: 1400px;
      margin: 0 auto;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }

    h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 400;
    }

    .actions {
      display: flex;
      gap: 8px;
    }

    .filters {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }

    input,
    button {
      padding: 8px 12px;
      border: 1px solid var(--divider-color);
      border-radius: 4px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      font-size: 14px;
    }

    button {
      cursor: pointer;
      transition: background 0.2s;
    }

    button:hover:not(:disabled) {
      background: var(--secondary-background-color);
    }

    button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    button.danger {
      color: var(--error-color);
    }

    .loading,
    .empty {
      text-align: center;
      padding: 48px;
      color: var(--secondary-text-color);
    }

    .table-container {
      overflow-x: auto;
      background: var(--card-background-color);
      border-radius: 4px;
      box-shadow: var(--ha-card-box-shadow);
    }

    table {
      width: 100%;
      border-collapse: collapse;
    }

    th,
    td {
      padding: 12px;
      text-align: left;
      border-bottom: 1px solid var(--divider-color);
    }

    th {
      font-weight: 500;
      cursor: pointer;
      user-select: none;
      background: var(--secondary-background-color);
    }

    th:hover {
      background: var(--divider-color);
    }

    .delete-btn {
      padding: 4px 8px;
      font-size: 12px;
      color: var(--error-color);
    }

    tbody tr:hover {
      background: var(--secondary-background-color);
    }
  `;
}

customElements.define("irrigation-sessions-panel", IrrigationSessionsPanel);
