import { api } from "./api.js";

const nf = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const one = new Intl.NumberFormat("en-UG", {minimumFractionDigits: 1, maximumFractionDigits: 1});
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

function latency(value) {
  if (value === null || value === undefined) return "—";
  const ms = Number(value);
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${nf.format(ms)}ms`;
}

function numberValue(selector, fallback) {
  const input = document.querySelector(selector);
  if (!input) return fallback;
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

export class PaymentsCdcSimulatorPage {
  constructor(shell) {
    this.shell = shell;
    this.timer = null;
    this.destroyed = false;
    this.loading = false;
    this.draft = {
      rate: 10,
      durationMinutes: 10,
      paymentCreatePct: 80,
      statusUpdatePct: 15,
      taxpayerMovePct: 5,
    };
  }

  async render() {
    this.destroyed = false;
    await this.refresh(true);
    this.schedulePoll();
    return this;
  }

  destroy() {
    this.destroyed = true;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = null;
  }

  captureDraft() {
    const form = document.querySelector("#payments-cdc-form");
    if (!form || form.dataset.running === "true") return;
    this.draft = {
      rate: numberValue("#payments-cdc-rate", this.draft.rate),
      durationMinutes: numberValue("#payments-cdc-duration", this.draft.durationMinutes),
      paymentCreatePct: numberValue("#payments-cdc-create-pct", this.draft.paymentCreatePct),
      statusUpdatePct: numberValue("#payments-cdc-update-pct", this.draft.statusUpdatePct),
      taxpayerMovePct: numberValue("#payments-cdc-move-pct", this.draft.taxpayerMovePct),
    };
  }

  schedulePoll() {
    if (this.destroyed) return;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(async () => {
      await this.refresh(false);
      this.schedulePoll();
    }, document.hidden ? 5000 : 1000);
  }

  async refresh(initial = false) {
    if (this.loading || this.destroyed) return;
    if (!initial) this.captureDraft();
    this.loading = true;
    try {
      const data = await api("/api/streaming-poc/status");
      if (!this.destroyed) this.renderState(data, initial);
    } catch (error) {
      if (!this.destroyed) this.renderUnavailable(error.message);
    } finally {
      this.loading = false;
    }
  }

  renderState(data, initial = false) {
    const running = data.state === "running" && Boolean(data.active);
    const run = data.active || data.run || {};
    const generated = Number(run.source_generated || 0);
    const received = Number(run.clickhouse_received || 0);
    const inFlight = Number(run.in_flight || 0);
    const rate = running ? Number(run.rate || 10) : this.draft.rate;
    const durationMinutes = running
      ? (run.duration_seconds ? Number(run.duration_seconds) / 60 : 0)
      : this.draft.durationMinutes;
    const paymentCreatePct = running ? Number(run.payment_create_pct ?? 80) : this.draft.paymentCreatePct;
    const statusUpdatePct = running ? Number(run.status_update_pct ?? 15) : this.draft.statusUpdatePct;
    const taxpayerMovePct = running ? Number(run.taxpayer_move_pct ?? 5) : this.draft.taxpayerMovePct;
    const actualSourceRate = Number(run.actual_source_rate || 0);
    const actualClickHouseRate = Number(run.actual_clickhouse_rate || 0);
    const mixTotal = paymentCreatePct + statusUpdatePct + taxpayerMovePct;

    this.shell.content.innerHTML = `<div class="sim-shell">
      <section class="sim-idle-hero">
        <div>
          <p class="eyebrow">Streaming analytics proof of concept</p>
          <h2>Payments & Taxpayer CDC Simulator</h2>
          <p>Simulate Payment transactions and Taxpayer station changes in Oracle and watch the real CDC path carry each change through Debezium and Kafka into ClickHouse.</p>
        </div>
        <div class="sim-architecture-mini" aria-label="CDC architecture">
          <span>Oracle</span><b>→</b><span>Debezium</span><b>→</b><span>Kafka</span><b>→</b><span>ClickHouse</span>
        </div>
      </section>

      <div class="sim-inline-notice">
        <strong>${running ? "Source workload running" : data.state === "failed" ? "Source workload stopped unexpectedly" : "Real CDC path"}</strong>
        <span>${running
          ? `Target ${one.format(rate)} events/sec · actual source ${one.format(actualSourceRate)}/s · ClickHouse arrivals ${one.format(actualClickHouseRate)}/s. The web app writes only to Oracle.`
          : "Set the source rate and traffic mix below. The simulator writes only to Oracle and never publishes directly to Kafka or ClickHouse."}</span>
      </div>

      <div class="sim-idle-grid">
        <section class="sim-panel sim-config-panel">
          <div class="sim-panel-head">
            <div><p class="eyebrow">Source workload</p><h3>${running ? "Simulation Running" : "Configure Simulation"}</h3></div>
            <span class="sim-safe-chip">Oracle source</span>
          </div>
          <form class="sim-config-form" id="payments-cdc-form" data-running="${running}">
            <label>
              <span>Target rate</span>
              <div class="sim-input-unit"><input id="payments-cdc-rate" class="input" type="number" min="0.1" max="1000" step="0.1" value="${escapeHtml(rate)}" ${running ? "disabled" : ""}><em>events/sec</em></div>
              <small>Each generated action is committed to the Oracle POC database.</small>
            </label>
            <label>
              <span>Duration</span>
              <div class="sim-input-unit"><input id="payments-cdc-duration" class="input" type="number" min="0" max="1440" step="1" value="${escapeHtml(durationMinutes)}" ${running ? "disabled" : ""}><em>minutes</em></div>
              <small>Use 0 for continuous mode; otherwise the backend stops the workload automatically.</small>
            </label>

            <div class="sim-target-preview">
              <span>Traffic mix — editable percentages</span>
              <div class="sim-config-form">
                <label>
                  <span>Payment create</span>
                  <div class="sim-input-unit"><input id="payments-cdc-create-pct" class="input" type="number" min="0" max="100" step="1" value="${escapeHtml(paymentCreatePct)}" ${running ? "disabled" : ""}><em>%</em></div>
                </label>
                <label>
                  <span>Status update</span>
                  <div class="sim-input-unit"><input id="payments-cdc-update-pct" class="input" type="number" min="0" max="100" step="1" value="${escapeHtml(statusUpdatePct)}" ${running ? "disabled" : ""}><em>%</em></div>
                </label>
                <label>
                  <span>Taxpayer move</span>
                  <div class="sim-input-unit"><input id="payments-cdc-move-pct" class="input" type="number" min="0" max="100" step="1" value="${escapeHtml(taxpayerMovePct)}" ${running ? "disabled" : ""}><em>%</em></div>
                </label>
              </div>
              <strong>${one.format(mixTotal)}%</strong>
              <small>The three percentages must total 100%.</small>
            </div>

            ${running
              ? `<button id="payments-cdc-stop" class="btn btn-danger sim-start-button" type="button"><span>■</span> Stop Simulation</button>`
              : `<button class="btn btn-primary sim-start-button" type="submit"><span>▶</span> Start Simulation</button>`}
          </form>
        </section>

        <div class="sim-idle-side">
          <section class="sim-panel">
            <div class="sim-panel-head"><div><p class="eyebrow">Demo scope</p><h3>CDC Use Cases</h3></div></div>
            <div class="sim-pop-grid">
              ${this.scopeCard(run.payments_received ?? "PAY", "Payment CDC events")}
              ${this.scopeCard(`${statusUpdatePct}%`, "Status update traffic")}
              ${this.scopeCard(run.taxpayer_changes_received ?? "TIN", "Taxpayer station changes")}
              ${this.scopeCard(received || "CDC", "Events received")}
            </div>
          </section>
          ${this.healthPanel(data.health || {})}
        </div>
      </div>

      <section class="sim-reconcile-grid" aria-label="CDC movement">
        ${this.reconcileCard("SOURCE", "Oracle", generated, "committed actions", running ? `${one.format(actualSourceRate)} events/sec actual` : run.started_at ? "Last workload" : "Waiting for a simulation", "source")}
        <div class="sim-flight-card"><span class="sim-flow-arrow">→</span><p>IN FLIGHT</p><strong>${nf.format(inFlight)}</strong><small>Debezium → Kafka</small><span class="sim-flow-arrow right">→</span></div>
        ${this.reconcileCard("DESTINATION", "ClickHouse", received, "CDC events received", received ? `${one.format(actualClickHouseRate)} events/sec arrived` : "Waiting for CDC delivery", "destination")}
      </section>

      <section class="sim-panel sim-events-panel">
        <div class="sim-panel-head">
          <div><p class="eyebrow">Event journey</p><h3>Live Payment & Taxpayer Events</h3></div>
          <span class="sim-panel-note">${running ? "1s refresh" : "latest run"}</span>
        </div>
        ${this.eventFeed(data.recent_events || [])}
      </section>
    </div>`;

    const form = document.querySelector("#payments-cdc-form");
    if (!running && form) {
      form.onsubmit = event => this.start(event);
      form.querySelectorAll("input").forEach(input => input.addEventListener("input", () => this.captureDraft()));
    }
    document.querySelector("#payments-cdc-stop")?.addEventListener("click", () => this.stop());

    if (initial && running) this.shell.toast("Reconnected to the active Payments CDC simulation");
  }

  async start(event) {
    event.preventDefault();
    this.captureDraft();
    const mixTotal = this.draft.paymentCreatePct + this.draft.statusUpdatePct + this.draft.taxpayerMovePct;
    if (Math.abs(mixTotal - 100) > 0.000001) {
      this.shell.toast(`Traffic mix must total 100%. Current total is ${mixTotal}.`, true);
      return;
    }

    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    button.innerHTML = `<span class="sim-spinner"></span> Starting…`;
    const payload = {
      rate: this.draft.rate,
      duration_seconds: Math.round(this.draft.durationMinutes * 60),
      payment_create_pct: this.draft.paymentCreatePct,
      status_update_pct: this.draft.statusUpdatePct,
      taxpayer_move_pct: this.draft.taxpayerMovePct,
    };
    try {
      await api("/api/streaming-poc/start", {method:"POST", body:JSON.stringify(payload)});
      this.shell.toast("Payments CDC source workload started");
      await this.refresh(false);
    } catch (error) {
      this.shell.toast(error.message, true);
      button.disabled = false;
      button.innerHTML = `<span>▶</span> Start Simulation`;
    }
  }

  async stop() {
    const button = document.querySelector("#payments-cdc-stop");
    if (button) { button.disabled = true; button.textContent = "Stopping…"; }
    try {
      await api("/api/streaming-poc/stop", {method:"POST"});
      this.shell.toast("Payments CDC source workload stopped");
      await this.refresh(false);
    } catch (error) {
      this.shell.toast(error.message, true);
      if (button) { button.disabled = false; button.innerHTML = `<span>■</span> Stop Simulation`; }
    }
  }

  scopeCard(value, label) {
    const rendered = typeof value === "number" ? nf.format(value) : escapeHtml(value);
    return `<div class="sim-pop-card"><strong>${rendered}</strong><span>${escapeHtml(label)}</span></div>`;
  }

  reconcileCard(kicker, name, count, verb, note, cls) {
    return `<div class="sim-reconcile-card ${cls}"><p>${kicker}</p><h3>${name}</h3><strong>${nf.format(Number(count || 0))}</strong><span>${escapeHtml(verb)}</span><small>${escapeHtml(note)}</small></div>`;
  }

  healthPanel(health) {
    const stages = [["oracle","Oracle"],["debezium","Debezium"],["kafka","Kafka"],["clickhouse","ClickHouse"]];
    return `<section class="sim-panel sim-health-panel">
      <div class="sim-panel-head"><div><p class="eyebrow">Pipeline</p><h3>CDC Components</h3></div><span class="sim-panel-note">live health</span></div>
      <div class="sim-health-grid">
        ${stages.map(([key,label]) => {
          const item = health[key] || {status:"unknown", detail:"Status unknown"};
          const icon = item.status === "healthy" ? "✓" : item.status === "degraded" ? "!" : item.status === "unavailable" ? "×" : "?";
          return `<div class="sim-health-card health-${escapeHtml(item.status)}"><span class="sim-health-icon">${icon}</span><div><strong>${label}</strong><b>${escapeHtml(item.status).toUpperCase()}</b><small>${escapeHtml(item.detail)}</small></div></div>`;
        }).join("")}
      </div>
    </section>`;
  }

  eventFeed(events) {
    if (!events.length) return `<div class="sim-events-empty"><span>⌁</span><strong>Waiting for streamed events</strong><p>Once Oracle commits an action, the matching ClickHouse CDC event will appear here with Kafka lineage.</p></div>`;
    return `<div class="sim-event-list">${events.map(event => `<article class="sim-event-row received">
      <div class="sim-event-main">
        <span class="sim-seq">${escapeHtml(event.event_type)}</span>
        <span class="sim-event-identity"><strong>${escapeHtml(event.entity_id)}</strong><small>${escapeHtml(event.taxpayer_id)}</small></span>
        <span class="sim-code">${escapeHtml(event.action)}</span>
        <span class="sim-event-message">${escapeHtml(event.detail)}</span>
        <span class="sim-event-path"><b>Oracle ✓</b><em>→</em><b class="arrived">ClickHouse ✓</b><small>${latency(event.cdc_latency_ms)}</small></span>
        <span class="sim-chevron">P${escapeHtml(event.kafka_partition ?? "—")} / ${escapeHtml(event.kafka_offset ?? "—")}</span>
      </div>
    </article>`).join("")}</div>`;
  }

  renderUnavailable(message) {
    this.shell.content.innerHTML = `<div class="sim-shell"><section class="analytics-unavailable"><div class="analytics-unavailable-icon">!</div><p class="eyebrow">Streaming POC unavailable</p><h2>Backend status cannot be loaded</h2><p>${escapeHtml(message)}</p><button class="btn btn-primary" id="payments-cdc-retry">Retry</button></section></div>`;
    document.querySelector("#payments-cdc-retry")?.addEventListener("click", () => this.refresh(true));
  }
}
