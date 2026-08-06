import { api } from "./api.js";

const nf = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const one = new Intl.NumberFormat("en-UG", {minimumFractionDigits: 1, maximumFractionDigits: 1});
const two = new Intl.NumberFormat("en-UG", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

function seconds(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const total = Math.max(0, Math.round(Number(value)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2,"0")}m ${String(s).padStart(2,"0")}s`;
  return `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
}

function latency(value) {
  if (value === null || value === undefined) return "—";
  const ms = Number(value);
  return ms >= 1000 ? `${two.format(ms / 1000)}s` : `${nf.format(ms)}ms`;
}

function statusMeta(status) {
  return {
    starting: ["STARTING", "Starting worker", "info"],
    running: ["RUNNING", "Source generation active", "success"],
    paused: ["PAUSED", "Source generation paused", "warning"],
    draining: ["DRAINING", "Waiting for CDC delivery", "warning"],
    completed: ["COMPLETED", "Source and destination reconciled", "success"],
    failed: ["FAILED", "Simulation stopped with an error", "danger"],
    stale: ["STALE", "Worker heartbeat was lost", "danger"],
  }[status] || [String(status || "UNKNOWN").toUpperCase(), "Status unavailable", "neutral"];
}

export class SimulatorPage {
  constructor(shell) {
    this.shell = shell;
    this.timer = null;
    this.destroyed = false;
    this.loading = false;
    this.visibilityHandler = null;
    this.configureNew = false;
  }

  async render() {
    this.destroyed = false;
    this.configureNew = false;
    this.shell.content.innerHTML = this.skeleton();
    this.visibilityHandler = () => {
      if (!document.hidden) this.refresh(false);
      this.schedulePoll();
    };
    document.addEventListener("visibilitychange", this.visibilityHandler);
    await this.refresh(true);
    this.schedulePoll();
    return this;
  }

  destroy() {
    this.destroyed = true;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = null;
    if (this.visibilityHandler) document.removeEventListener("visibilitychange", this.visibilityHandler);
  }

  schedulePoll() {
    if (this.destroyed) return;
    if (this.timer) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(async () => {
      await this.refresh(false);
      this.schedulePoll();
    }, document.hidden ? 5000 : 1000);
  }

  skeleton() {
    return `<div class="sim-shell">
      <section class="sim-hero sim-skeleton-card"><div class="sim-skeleton-line wide"></div><div class="sim-skeleton-line"></div></section>
      <div class="sim-reconcile-grid"><div class="sim-skeleton-card tall"></div><div class="sim-skeleton-card tall"></div><div class="sim-skeleton-card tall"></div></div>
      <div class="sim-skeleton-card huge"></div>
    </div>`;
  }

  async refresh(initial = false) {
    if (this.loading || this.destroyed) return;
    this.loading = true;
    try {
      const data = await api("/api/simulator/status");
      if (this.destroyed) return;
      if (this.configureNew) {
        this.renderIdle(data, true);
      } else if (data.active) {
        if (initial && ["starting","running","paused","draining"].includes(data.active.status)) {
          this.shell.toast(`Reconnected to active simulation ${data.active.run_id}`);
        }
        this.renderRun(data);
      } else {
        this.renderIdle(data, false);
      }
    } catch (error) {
      if (!this.destroyed) this.renderUnavailable(error.message);
    } finally {
      this.loading = false;
    }
  }

  renderIdle(data, fromCompleted) {
    const defaults = data.defaults || {rate:14,duration_seconds:600,retry_probability:.12};
    const population = data.population || {taxpayers:200,devices:500,stations:20,error_codes:15};
    this.shell.content.innerHTML = `<div class="sim-shell">
      <section class="sim-idle-hero">
        <div>
          <p class="eyebrow">Controlled source workload</p>
          <h2>EFRIS Simulator Control Room</h2>
          <p>Generate realistic EFRIS invoice-error traffic in Oracle and watch the real CDC path carry it to ClickHouse.</p>
        </div>
        <div class="sim-architecture-mini" aria-label="CDC architecture">
          <span>Oracle</span><b>→</b><span>Debezium</span><b>→</b><span>Kafka</span><b>→</b><span>ClickHouse</span>
        </div>
      </section>

      ${fromCompleted ? `<div class="sim-inline-notice"><strong>New run configuration</strong><span>Your previous run remains available in history. Starting a new run creates a new traceable source prefix.</span></div>` : ""}

      <div class="sim-idle-grid">
        <section class="sim-panel sim-config-panel">
          <div class="sim-panel-head"><div><p class="eyebrow">Workload</p><h3>Configure Simulation</h3></div><span class="sim-safe-chip">Refresh-safe</span></div>
          <form id="sim-start-form" class="sim-config-form">
            <label><span>Target rate</span><div class="sim-input-unit"><input id="sim-rate" class="input" type="number" min="0.1" max="1000" step="0.1" value="${escapeHtml(defaults.rate)}" required><em>events/sec</em></div><small>Individual Oracle INSERT + COMMIT transactions.</small></label>
            <label><span>Duration</span><div class="sim-input-unit"><input id="sim-duration" class="input" type="number" min="0" max="1440" step="1" value="${Number(defaults.duration_seconds)/60}" required><em>minutes</em></div><small>Use 0 for continuous mode.</small></label>
            <label><span>Retry probability</span><div class="sim-input-unit"><input id="sim-retry" class="input" type="number" min="0" max="100" step="1" value="${Math.round(Number(defaults.retry_probability)*100)}" required><em>%</em></div><small>Retries reuse the same TIN + seller reference.</small></label>
            <div class="sim-target-preview"><span>Expected source events</span><strong id="sim-expected">8,400</strong><small id="sim-target-copy">for 10 minutes at 14 events/sec</small></div>
            <button class="btn btn-primary sim-start-button" type="submit"><span>▶</span> Start Simulation</button>
          </form>
        </section>
        <div class="sim-idle-side">
          <section class="sim-panel">
            <div class="sim-panel-head"><div><p class="eyebrow">Synthetic population</p><h3>Demo Coverage</h3></div></div>
            <div class="sim-pop-grid">
              ${this.populationMetric(population.taxpayers, "Taxpayers")}
              ${this.populationMetric(population.devices, "Devices")}
              ${this.populationMetric(population.stations, "Stations")}
              ${this.populationMetric(population.error_codes, "Error codes")}
            </div>
          </section>
          ${this.healthPanel(data.health || {})}
          ${this.historyPanel(data.history || [])}
        </div>
      </div>
    </div>`;

    const rate = document.querySelector("#sim-rate");
    const duration = document.querySelector("#sim-duration");
    const updateExpected = () => {
      const r = Number(rate.value || 0), minutes = Number(duration.value || 0);
      const expected = minutes === 0 ? null : Math.round(r * minutes * 60);
      document.querySelector("#sim-expected").textContent = expected === null ? "Continuous" : nf.format(expected);
      document.querySelector("#sim-target-copy").textContent = minutes === 0 ? `${one.format(r)} events/sec until stopped` : `for ${one.format(minutes)} minutes at ${one.format(r)} events/sec`;
    };
    updateExpected();
    rate.oninput = updateExpected;
    duration.oninput = updateExpected;
    document.querySelector("#sim-start-form").onsubmit = event => this.start(event);
  }

  populationMetric(value, label) {
    return `<div class="sim-pop-card"><strong>${nf.format(Number(value || 0))}</strong><span>${escapeHtml(label)}</span></div>`;
  }

  async start(event) {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    button.innerHTML = `<span class="sim-spinner"></span> Starting…`;
    const payload = {
      rate: Number(document.querySelector("#sim-rate").value),
      duration_seconds: Math.round(Number(document.querySelector("#sim-duration").value) * 60),
      retry_probability: Number(document.querySelector("#sim-retry").value) / 100,
    };
    try {
      const run = await api("/api/simulator/runs", {method:"POST", body:JSON.stringify(payload)});
      this.configureNew = false;
      this.shell.toast(`Simulation ${run.run_id} is starting`);
      await this.refresh(false);
    } catch (error) {
      if (error.code === "simulation_already_running" && error.details?.active_run) {
        this.configureNew = false;
        this.shell.toast(`Simulation ${error.details.active_run.run_id} is already active`);
        await this.refresh(false);
      } else {
        this.shell.toast(error.message, true);
        button.disabled = false;
        button.innerHTML = `<span>▶</span> Start Simulation`;
      }
    }
  }

  renderRun(data) {
    const run = data.active;
    const [label, helper, tone] = statusMeta(run.status);
    const progress = run.progress_percent === null ? null : Math.max(0, Math.min(100, Number(run.progress_percent || 0)));
    const sourceNote = run.source_count_exact === false ? "Worker counter · Oracle check unavailable" : "Exact rows in Oracle";
    const stateCopy = run.status === "paused"
      ? "Source generation is paused. CDC is still draining already committed events."
      : run.status === "draining"
        ? "Source generation has ended. Waiting for every committed event to arrive in ClickHouse."
        : run.status === "completed"
          ? "Oracle and ClickHouse are reconciled for this run."
          : helper;

    this.shell.content.innerHTML = `<div class="sim-shell">
      <section class="sim-run-hero tone-${tone}">
        <div class="sim-run-title">
          <div class="sim-status-badge tone-${tone}"><span class="sim-status-dot"></span>${label}</div>
          <p class="eyebrow">EFRIS workload run</p>
          <h2>${escapeHtml(run.run_id)}</h2>
          <p>${escapeHtml(stateCopy)}</p>
        </div>
        <div class="sim-run-actions">${this.runActions(run)}</div>
        <div class="sim-run-meta">
          <div><span>Source prefix</span><strong>${escapeHtml(run.source_prefix)}</strong></div>
          <div><span>Target</span><strong>${two.format(Number(run.rate || 0))}/s</strong></div>
          <div><span>Actual</span><strong>${two.format(Number(run.actual_source_rate || 0))}/s</strong></div>
          <div><span>Active time</span><strong>${seconds(run.active_elapsed_seconds)}</strong></div>
          <div><span>Remaining</span><strong>${run.target_events === null ? "Continuous" : seconds(run.remaining_seconds)}</strong></div>
        </div>
        ${progress === null ? `<div class="sim-progress-copy"><strong>${nf.format(run.generated)} generated</strong><span>Continuous run</span></div>` : `
          <div class="sim-progress-row"><div class="sim-progress-track"><div class="sim-progress-fill" style="width:${progress}%"></div></div><strong>${two.format(progress)}%</strong></div>
          <div class="sim-progress-copy"><span>${nf.format(run.generated)} generated</span><span>${nf.format(run.target_events)} target</span></div>`}
      </section>

      <section class="sim-reconcile-grid" aria-label="Run reconciliation">
        ${this.reconcileCard("SOURCE", "Oracle", run.oracle_committed, "committed", sourceNote, "source")}
        <div class="sim-flight-card"><span class="sim-flow-arrow">→</span><p>IN FLIGHT</p><strong>${nf.format(run.in_flight || 0)}</strong><small>${run.in_flight ? "committed events still travelling" : "no known backlog"}</small><span class="sim-flow-arrow right">→</span></div>
        ${this.reconcileCard("DESTINATION", "ClickHouse", run.clickhouse_received, "received", `${two.format(Number(run.delivery_percent || 0))}% delivered`, "destination")}
      </section>

      ${this.healthPanel(data.health || run.health || {})}

      <section class="sim-kpi-grid">
        ${this.kpi(run.metrics?.error_events, "Error events", "Rows received for this run")}
        ${this.kpi(run.metrics?.affected_invoices, "Affected invoices", "Distinct TIN + reference")}
        ${this.kpi(run.metrics?.retry_events, "Retry events", "Repeated business references")}
        ${this.kpi(run.metrics?.taxpayers, "Taxpayers", "Distinct TINs represented")}
        ${this.kpi(run.metrics?.devices, "Devices", "Distinct source devices")}
        ${this.kpi(run.metrics?.error_codes, "Error codes", "Distinct return codes")}
      </section>

      <div class="sim-live-grid">
        <section class="sim-panel sim-throughput-panel">
          <div class="sim-panel-head"><div><p class="eyebrow">Live throughput</p><h3>Source Rate & Arrivals</h3></div><span class="sim-panel-note">1s refresh</span></div>
          ${this.throughputChart(run.source_rate_samples || [], run.throughput || [])}
        </section>
        <section class="sim-panel sim-latency-panel">
          <div class="sim-panel-head"><div><p class="eyebrow">CDC latency</p><h3>Oracle Commit → ClickHouse</h3></div><span class="sim-panel-note">real timestamps</span></div>
          ${this.latencyPanel(run.latency || {})}
        </section>
      </div>

      <section class="sim-panel sim-events-panel">
        <div class="sim-panel-head"><div><p class="eyebrow">Event journey</p><h3>Live Run Events</h3></div><span class="sim-panel-note">latest ${Math.min(40,(run.recent_events || []).length)}</span></div>
        ${this.eventFeed(run.recent_events || [])}
      </section>

      ${this.historyPanel(data.history || [], run.run_id)}
    </div>`;

    document.querySelector("#sim-pause")?.addEventListener("click", () => this.control(run, "pause"));
    document.querySelector("#sim-resume")?.addEventListener("click", () => this.control(run, "resume"));
    document.querySelector("#sim-stop")?.addEventListener("click", () => this.confirmStop(run));
    document.querySelector("#sim-new-run")?.addEventListener("click", () => { this.configureNew = true; this.renderIdle(data, true); });
    document.querySelectorAll("[data-event-toggle]").forEach(button => button.onclick = () => {
      const detail = document.querySelector(`#${button.dataset.eventToggle}`);
      if (detail) detail.classList.toggle("hidden");
    });
  }

  runActions(run) {
    if (run.status === "running") return `<button id="sim-pause" class="btn sim-control"><span>Ⅱ</span> Pause</button><button id="sim-stop" class="btn btn-danger"><span>■</span> Stop Run</button>`;
    if (run.status === "paused") return `<button id="sim-resume" class="btn btn-success"><span>▶</span> Resume</button><button id="sim-stop" class="btn btn-danger"><span>■</span> Stop Run</button>`;
    if (run.status === "starting") return `<button class="btn" disabled>Starting worker…</button><button id="sim-stop" class="btn btn-danger">Stop Run</button>`;
    if (["completed","failed","stale"].includes(run.status)) return `<button id="sim-new-run" class="btn btn-primary"><span>＋</span> Start New Run</button>`;
    return `<button class="btn" disabled>CDC is draining…</button>`;
  }

  reconcileCard(kicker, name, count, verb, note, cls) {
    return `<div class="sim-reconcile-card ${cls}"><p>${kicker}</p><h3>${name}</h3><strong>${nf.format(Number(count || 0))}</strong><span>${verb}</span><small>${escapeHtml(note)}</small></div>`;
  }

  kpi(value, label, note) {
    return `<div class="sim-kpi"><span>${escapeHtml(label)}</span><strong>${nf.format(Number(value || 0))}</strong><small>${escapeHtml(note)}</small></div>`;
  }

  healthPanel(health) {
    const stages = [["oracle","Oracle"],["debezium","Debezium"],["kafka","Kafka"],["clickhouse","ClickHouse"]];
    return `<section class="sim-panel sim-health-panel"><div class="sim-panel-head"><div><p class="eyebrow">Pipeline health</p><h3>CDC Components</h3></div><span class="sim-panel-note">health ≠ per-event proof</span></div><div class="sim-health-grid">${stages.map(([key,label]) => {
      const item = health[key] || {status:"unknown",detail:"Status unknown"};
      const icon = item.status === "healthy" ? "✓" : item.status === "degraded" ? "!" : item.status === "unavailable" ? "×" : "?";
      return `<div class="sim-health-card health-${escapeHtml(item.status)}"><span class="sim-health-icon">${icon}</span><div><strong>${label}</strong><b>${escapeHtml(item.status).toUpperCase()}</b><small>${escapeHtml(item.detail)}</small></div></div>`;
    }).join("")}</div></section>`;
  }

  throughputChart(sourceSamples, arrivalSamples) {
    const source = sourceSamples.slice(-30);
    const arrivals = arrivalSamples.slice(-12);
    const maxRate = Math.max(1, ...source.map(s => Number(s.rate || 0)), ...arrivals.map(s => Number(s.arrived || 0) / 5));
    const bars = source.length ? source.map(sample => {
      const height = Math.max(4, Math.round(Number(sample.rate || 0) / maxRate * 100));
      return `<i style="height:${height}%" title="${two.format(Number(sample.rate || 0))}/s"></i>`;
    }).join("") : `<div class="sim-chart-empty">Waiting for source-rate samples…</div>`;
    const arrivalRate = arrivals.length ? Number(arrivals[arrivals.length-1].arrived || 0) / 5 : 0;
    const currentSource = source.length ? Number(source[source.length-1].rate || 0) : 0;
    return `<div class="sim-throughput-body"><div class="sim-chart-summary"><div><span>Current source</span><strong>${two.format(currentSource)}/s</strong></div><div><span>Latest ClickHouse arrival</span><strong>${two.format(arrivalRate)}/s</strong></div></div><div class="sim-mini-bars">${bars}</div><div class="sim-chart-axis"><span>older</span><span>source rate samples</span><span>now</span></div></div>`;
  }

  latencyPanel(latencyData) {
    const rows = [["P50",latencyData.p50_ms],["P95",latencyData.p95_ms],["P99",latencyData.p99_ms],["MAX",latencyData.max_ms]];
    return `<div class="sim-latency-body"><div class="sim-latency-primary"><span>Average</span><strong>${latency(latencyData.avg_ms)}</strong><small>Measured from Debezium source commit timestamp to ClickHouse ingestion.</small></div><div class="sim-latency-grid">${rows.map(([label,value]) => `<div><span>${label}</span><strong>${latency(value)}</strong></div>`).join("")}</div></div>`;
  }

  eventFeed(events) {
    if (!events.length) return `<div class="sim-events-empty"><span>⌁</span><strong>Waiting for source events</strong><p>Committed Oracle events will appear here and then flip to ClickHouse received when CDC catches up.</p></div>`;
    return `<div class="sim-event-list">${events.map((event,index) => {
      const received = Boolean(event.clickhouse_received);
      const detailId = `sim-event-${index}`;
      return `<article class="sim-event-row ${received ? "received" : "pending"}">
        <button class="sim-event-main" type="button" data-event-toggle="${detailId}">
          <span class="sim-seq">#${String(event.sequence ?? "—").padStart(6,"0")}</span>
          <span class="sim-event-identity"><strong>${escapeHtml(event.tin)}</strong><small>${escapeHtml(event.device_no)}</small></span>
          <span class="sim-code">${escapeHtml(event.return_code)}</span>
          <span class="sim-event-message">${escapeHtml(event.return_msg || "—")}</span>
          <span class="sim-event-path"><b>Oracle ✓</b><em>→</em>${received ? `<b class="arrived">ClickHouse ✓</b><small>${latency(event.cdc_latency_ms)}</small>` : `<b class="waiting">Waiting for CDC…</b>`}</span>
          <span class="sim-chevron">⌄</span>
        </button>
        <div id="${detailId}" class="sim-event-detail hidden">
          <div><span>Source ID</span><strong>${escapeHtml(event.source_id)}</strong></div>
          <div><span>Seller reference</span><strong>${escapeHtml(event.seller_reference_no)}</strong></div>
          <div><span>Source commit</span><strong>${escapeHtml(event.source_commit_ts || "Waiting for downstream evidence")}</strong></div>
          <div><span>SCN / Commit SCN</span><strong>${escapeHtml(event.source_scn || "—")} / ${escapeHtml(event.source_commit_scn || "—")}</strong></div>
          <div><span>Kafka lineage</span><strong>${event.kafka_partition === null ? "—" : `Partition ${escapeHtml(event.kafka_partition)} · Offset ${escapeHtml(event.kafka_offset)}`}</strong></div>
          <div><span>ClickHouse ingestion</span><strong>${escapeHtml(event.ingested_at || "—")}</strong></div>
        </div>
      </article>`;
    }).join("")}</div>`;
  }

  historyPanel(history, currentRunId = null) {
    if (!history.length) return `<section class="sim-panel sim-history"><div class="sim-panel-head"><div><p class="eyebrow">Run history</p><h3>Previous Runs</h3></div></div><div class="sim-history-empty">No completed simulator runs yet.</div></section>`;
    return `<section class="sim-panel sim-history"><div class="sim-panel-head"><div><p class="eyebrow">Run history</p><h3>Previous Runs</h3></div></div><div class="sim-history-list">${history.slice(0,8).map(run => {
      const [label,,tone] = statusMeta(run.status);
      return `<div class="sim-history-row ${run.run_id === currentRunId ? "current" : ""}"><span class="sim-history-status tone-${tone}">${label}</span><strong>${escapeHtml(run.run_id)}</strong><span>${two.format(Number(run.rate || 0))}/s</span><span>${nf.format(Number(run.generated || 0))} events</span><span>${seconds(run.active_elapsed_seconds)}</span></div>`;
    }).join("")}</div></section>`;
  }

  async control(run, action) {
    try {
      await api(`/api/simulator/runs/${encodeURIComponent(run.run_id)}/${action}`, {method:"POST"});
      const copy = action === "pause" ? "Pause requested" : "Resume requested";
      this.shell.toast(`${copy} for ${run.run_id}`);
      await this.refresh(false);
    } catch (error) {
      this.shell.toast(error.message, true);
    }
  }

  confirmStop(run) {
    this.shell.openDrawer(`<div class="drawer-head"><div><p class="eyebrow">Final action</p><h3>Stop Simulation?</h3></div><button class="close-btn" data-close>×</button></div>
      <div class="sim-stop-warning"><span>■</span><div><strong>${escapeHtml(run.run_id)}</strong><p>Stopping ends source generation permanently for this run. Already committed Oracle rows are kept, and CDC will continue draining them into ClickHouse.</p></div></div>
      <div class="detail-grid"><div class="detail"><span>Oracle committed</span><strong>${nf.format(run.oracle_committed || 0)}</strong></div><div class="detail"><span>In flight</span><strong>${nf.format(run.in_flight || 0)}</strong></div></div>
      <div class="form-actions"><button class="btn" data-close>Keep Running</button><button id="confirm-sim-stop" class="btn btn-danger">Stop Run</button></div>`);
    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
    document.querySelector("#confirm-sim-stop").onclick = async () => {
      const button = document.querySelector("#confirm-sim-stop");
      button.disabled = true; button.textContent = "Stopping…";
      try {
        await api(`/api/simulator/runs/${encodeURIComponent(run.run_id)}/stop`, {method:"POST"});
        this.shell.closeDrawer();
        this.shell.toast(`Simulation ${run.run_id} is stopping; CDC will continue draining`);
        await this.refresh(false);
      } catch (error) {
        this.shell.toast(error.message, true);
        button.disabled = false; button.textContent = "Stop Run";
      }
    };
  }

  renderUnavailable(message) {
    this.shell.content.innerHTML = `<div class="sim-shell"><section class="analytics-unavailable"><div class="analytics-unavailable-icon">!</div><p class="eyebrow">Simulator unavailable</p><h2>Control Room cannot be loaded</h2><p>${escapeHtml(message)}</p><p class="muted">An already-running detached simulator worker is not stopped by this browser error.</p><button class="btn btn-primary" id="sim-retry">Retry</button></section></div>`;
    document.querySelector("#sim-retry").onclick = () => this.refresh(true);
  }
}
