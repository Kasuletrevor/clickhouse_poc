import { api } from "./api.js";

const money = new Intl.NumberFormat("en-UG", {
  style: "currency",
  currency: "UGX",
  maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const compact = new Intl.NumberFormat("en-UG", {notation: "compact", maximumFractionDigits: 2});
const when = (value) => value ? new Date(value).toLocaleString("en-UG", {dateStyle:"medium", timeStyle:"short"}) : "—";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
const statusBadge = (status) => `<span class="badge badge-${String(status).toLowerCase()}">${escapeHtml(status)}</span>`;

export class DashboardPage {
  constructor(shell) {
    this.shell = shell;
    this.timer = null;
    this.loading = false;
    this.destroyed = false;
    this.hasRenderedData = false;
  }

  async render() {
    this.destroyed = false;
    this.shell.content.innerHTML = `
      <div class="dashboard-head">
        <div>
          <p class="eyebrow">Revenue & transaction overview</p>
          <h2>Business Dashboard</h2>
          <p>Current analytical view of taxpayers, stations and payment activity.</p>
        </div>
        <div class="dashboard-refresh"><span class="environment-dot"></span><span>Last refreshed <strong id="dashboard-refreshed">Loading…</strong></span></div>
      </div>
      <div id="dashboard-kpis" class="dashboard-kpi-grid">
        ${this.kpiSkeleton("Total Taxpayers")}
        ${this.kpiSkeleton("Total Stations")}
        ${this.kpiSkeleton("Payments Today")}
        ${this.kpiSkeleton("Amount Collected Today")}
      </div>
      <div class="dashboard-chart-grid">
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Collection performance</p><h3>Payments by Station</h3></div><span class="dashboard-panel-note">Successful amount</span></div>
          <div id="station-chart" class="dashboard-chart loading">Loading station performance…</div>
        </section>
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Transaction mix</p><h3>Payment Status</h3></div><span class="dashboard-panel-note">Current state</span></div>
          <div id="status-chart" class="dashboard-chart loading">Loading payment status…</div>
        </section>
      </div>
      <div class="dashboard-lower-grid">
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Latest transactions</p><h3>Recent Payments</h3></div></div>
          <div id="recent-payments" class="loading">Loading recent payments…</div>
        </section>
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Master data changes</p><h3>Recent Taxpayer Activity</h3></div><span class="dashboard-panel-note">Source activity</span></div>
          <div id="taxpayer-activity" class="loading">Loading taxpayer activity…</div>
        </section>
      </div>`;

    await this.refresh(true);
    if (!this.destroyed) this.timer = window.setInterval(() => this.refresh(false), 10000);
    return this;
  }

  destroy() {
    this.destroyed = true;
    if (this.timer) window.clearInterval(this.timer);
    this.timer = null;
  }

  kpiSkeleton(label) {
    return `<div class="dashboard-kpi-card"><span class="dashboard-kpi-label">${label}</span><strong class="dashboard-kpi-value muted">—</strong><small>Loading analytics…</small></div>`;
  }

  async refresh(initial) {
    if (this.loading || this.destroyed) return;
    this.loading = true;
    try {
      const [summary, stations, statuses, activity] = await Promise.all([
        api("/api/dashboard/summary"),
        api("/api/dashboard/payments-by-station"),
        api("/api/dashboard/status-summary"),
        api("/api/dashboard/recent-activity"),
      ]);
      if (this.destroyed) return;
      this.renderKpis(summary);
      this.renderStationChart(stations);
      this.renderStatusChart(statuses);
      this.renderRecentPayments(activity.recent_payments || []);
      this.renderTaxpayerActivity(activity.recent_taxpayer_activity || []);
      const refreshed = document.querySelector("#dashboard-refreshed");
      if (refreshed) refreshed.textContent = when(summary.refreshed_at);
      this.hasRenderedData = true;
    } catch (error) {
      if (this.destroyed) return;
      if (!this.hasRenderedData || initial) this.renderUnavailable(error.message);
      else this.shell.toast(`Dashboard refresh failed: ${error.message}`, true);
    } finally {
      this.loading = false;
    }
  }

  renderUnavailable(message) {
    this.shell.content.innerHTML = `
      <div class="analytics-unavailable">
        <div class="analytics-unavailable-icon">!</div>
        <p class="eyebrow">Analytics unavailable</p>
        <h2>Dashboard data cannot be loaded right now</h2>
        <p>${escapeHtml(message)}</p>
        <p class="muted">Source-system Payments, Taxpayers and Stations remain available.</p>
        <button class="btn btn-primary" id="dashboard-retry">Retry</button>
      </div>`;
    document.querySelector("#dashboard-retry").onclick = () => this.render();
  }

  renderKpis(s) {
    const items = [
      ["TOTAL TAXPAYERS", number.format(Number(s.total_taxpayers || 0)), "Current taxpayer records", ""],
      ["TOTAL STATIONS", number.format(Number(s.total_stations || 0)), "Current station records", ""],
      ["PAYMENTS TODAY", number.format(Number(s.payments_today || 0)), "Business day · Africa/Kampala", ""],
      ["AMOUNT COLLECTED TODAY", `UGX ${compact.format(Number(s.amount_collected_today || 0))}`, money.format(Number(s.amount_collected_today || 0)), " dashboard-kpi-money"],
    ];
    document.querySelector("#dashboard-kpis").innerHTML = items.map(([label,value,note,extra]) => `
      <div class="dashboard-kpi-card${extra}">
        <div class="dashboard-kpi-accent"></div>
        <span class="dashboard-kpi-label">${label}</span>
        <strong class="dashboard-kpi-value">${escapeHtml(value)}</strong>
        <small>${escapeHtml(note)}</small>
      </div>`).join("");
  }

  renderStationChart(rows) {
    const target = document.querySelector("#station-chart");
    if (!rows.length) { target.innerHTML = `<div class="empty">No payment activity is available yet.</div>`; return; }
    const data = rows.slice(0, 8);
    const max = Math.max(...data.map(r => Number(r.successful_amount || 0)), 1);
    const width = 760, labelWidth = 180, valueWidth = 130, chartWidth = width - labelWidth - valueWidth;
    const rowHeight = 52, height = data.length * rowHeight + 18;
    const bars = data.map((row, index) => {
      const value = Number(row.successful_amount || 0);
      const barWidth = Math.max(value > 0 ? 4 : 0, (value / max) * chartWidth);
      const y = index * rowHeight + 13;
      const cls = index === 0 ? "dashboard-bar dashboard-bar-primary" : "dashboard-bar";
      const station = escapeHtml(row.station_name || "Unassigned");
      return `
        <g>
          <text x="0" y="${y + 15}" class="chart-label">${station}</text>
          <rect x="${labelWidth}" y="${y}" width="${chartWidth}" height="22" rx="6" class="dashboard-bar-track"></rect>
          <rect x="${labelWidth}" y="${y}" width="${barWidth}" height="22" rx="6" class="${cls}"><title>${station}: ${money.format(value)} · ${row.payment_count} payments</title></rect>
          <text x="${width - 4}" y="${y + 15}" text-anchor="end" class="chart-value">UGX ${compact.format(value)}</text>
        </g>`;
    }).join("");
    target.classList.remove("loading");
    target.innerHTML = `<svg class="station-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Successful payment amount by station">${bars}</svg>`;
  }

  renderStatusChart(rows) {
    const target = document.querySelector("#status-chart");
    const statuses = ["SUCCESSFUL", "PENDING", "REVERSED"].map(status => rows.find(r => r.status === status) || {status, payment_count:0, amount:0});
    const total = statuses.reduce((sum, row) => sum + Number(row.payment_count || 0), 0);
    const radius = 62, circumference = 2 * Math.PI * radius;
    let offset = 0;
    const circles = statuses.map(row => {
      const count = Number(row.payment_count || 0);
      const length = total ? (count / total) * circumference : 0;
      const currentOffset = -offset;
      offset += length;
      return `<circle class="donut-segment donut-${row.status.toLowerCase()}" cx="90" cy="90" r="${radius}" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${currentOffset}" transform="rotate(-90 90 90)"><title>${row.status}: ${count}</title></circle>`;
    }).join("");
    const legend = statuses.map(row => {
      const count = Number(row.payment_count || 0);
      const pct = total ? Math.round((count / total) * 100) : 0;
      return `<div class="status-legend-row"><span class="status-dot dot-${row.status.toLowerCase()}"></span><span>${row.status}</span><strong>${number.format(count)}</strong><small>${pct}%</small></div>`;
    }).join("");
    target.classList.remove("loading");
    target.innerHTML = `<div class="donut-layout"><svg class="donut-svg" viewBox="0 0 180 180" role="img" aria-label="Payment status breakdown"><circle class="donut-track" cx="90" cy="90" r="${radius}"></circle>${circles}<text x="90" y="85" text-anchor="middle" class="donut-total">${number.format(total)}</text><text x="90" y="105" text-anchor="middle" class="donut-caption">payments</text></svg><div class="status-legend">${legend}</div></div>`;
  }

  renderRecentPayments(rows) {
    const target = document.querySelector("#recent-payments");
    if (!rows.length) { target.innerHTML = `<div class="empty">No recent payments are available.</div>`; return; }
    target.classList.remove("loading");
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table"><thead><tr><th>Payment</th><th>Taxpayer</th><th>Amount</th><th>Status</th><th>Station</th></tr></thead><tbody>${rows.map(p => `<tr><td><strong>${escapeHtml(p.payment_id)}</strong><br><span class="muted">${escapeHtml(when(p.payment_time))}</span></td><td>${escapeHtml(p.taxpayer_name || p.taxpayer_id)}<br><span class="muted">${escapeHtml(p.taxpayer_id)}</span></td><td class="money">${escapeHtml(money.format(Number(p.amount || 0)))}</td><td>${statusBadge(p.status)}</td><td>${escapeHtml(p.station_at_payment || "—")}</td></tr>`).join("")}</tbody></table></div>`;
  }

  renderTaxpayerActivity(rows) {
    const target = document.querySelector("#taxpayer-activity");
    if (!rows.length) { target.innerHTML = `<div class="empty">No recent taxpayer changes are available.</div>`; return; }
    target.classList.remove("loading");
    target.innerHTML = `<div class="activity-feed">${rows.map(row => `
      <article class="activity-item">
        <div class="activity-marker"></div>
        <div class="activity-copy">
          <div class="activity-top"><strong>${escapeHtml(row.taxpayer_id)}</strong><time>${escapeHtml(when(row.occurred_at))}</time></div>
          <span class="activity-action">${escapeHtml(row.action)}</span>
          <p>${escapeHtml(row.message || row.taxpayer_name || "")}</p>
        </div>
      </article>`).join("")}</div>`;
  }
}
