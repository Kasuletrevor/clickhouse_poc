import { api } from "./api.js";

const number = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const compact = new Intl.NumberFormat("en-UG", {notation: "compact", maximumFractionDigits: 2});
const money = new Intl.NumberFormat("en-UG", {style: "currency", currency: "UGX", maximumFractionDigits: 0});
const when = (value) => value ? new Date(value).toLocaleString("en-UG", {dateStyle:"medium", timeStyle:"short"}) : "—";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'\"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'\"':"&quot;"}[ch]));

export class EfrisErrorsPage {
  constructor(shell) {
    this.shell = shell;
    this.timer = null;
    this.loading = false;
    this.destroyed = false;
    this.hasRenderedData = false;
    this.minutes = 60;
  }

  async render() {
    this.destroyed = false;
    this.hasRenderedData = false;
    if (this.timer) window.clearInterval(this.timer);
    this.timer = null;
    this.shell.content.innerHTML = `
      <div class="dashboard-head">
        <div>
          <p class="eyebrow">EFRIS analytical monitoring</p>
          <h2>EFRIS Error Monitor</h2>
          <p>Live invoice-error activity captured from Oracle and served from ClickHouse.</p>
        </div>
        <div class="efris-head-actions">
          <select id="efris-range" class="select efris-range" aria-label="EFRIS time range">
            <option value="15">Last 15 minutes</option>
            <option value="60" selected>Last 1 hour</option>
            <option value="1440">Last 24 hours</option>
            <option value="10080">Last 7 days</option>
          </select>
          <div class="dashboard-refresh"><span class="environment-dot"></span><span>Last refreshed <strong id="efris-refreshed">Loading…</strong></span></div>
        </div>
      </div>
      <div id="efris-kpis" class="efris-kpi-grid">
        ${this.kpiSkeleton("Error Events")}
        ${this.kpiSkeleton("Affected Invoices")}
        ${this.kpiSkeleton("Taxpayers")}
        ${this.kpiSkeleton("Devices")}
        ${this.kpiSkeleton("UGX Gross Amount")}
        ${this.kpiSkeleton("UGX Tax Amount")}
      </div>
      <div class="dashboard-chart-grid efris-chart-grid">
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Volume trend</p><h3>Error Events Over Time</h3></div><span class="dashboard-panel-note">Live CDC</span></div>
          <div id="efris-trend" class="dashboard-chart loading">Loading error trend…</div>
        </section>
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Root causes</p><h3>Top Error Codes</h3></div></div>
          <div id="efris-codes" class="loading">Loading error codes…</div>
        </section>
      </div>
      <div class="dashboard-lower-grid">
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Latest source activity</p><h3>Recent Error Events</h3></div><span class="dashboard-panel-note">Oracle → Kafka → ClickHouse</span></div>
          <div id="efris-recent" class="loading">Loading recent errors…</div>
        </section>
        <section class="dashboard-panel">
          <div class="dashboard-panel-head"><div><p class="eyebrow">Concentration</p><h3>Top Taxpayers</h3></div></div>
          <div id="efris-taxpayers" class="loading">Loading taxpayers…</div>
        </section>
      </div>`;

    document.querySelector("#efris-range").onchange = async (event) => {
      this.minutes = Number(event.target.value || 60);
      await this.refresh(false);
    };

    await this.refresh(true);
    if (!this.destroyed && this.hasRenderedData) {
      this.timer = window.setInterval(() => this.refresh(false), 5000);
    }
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
      const data = await api(`/api/efris-errors/dashboard?minutes=${this.minutes}`);
      if (this.destroyed) return;
      this.renderKpis(data.summary || {});
      this.renderTrend(data.trend || []);
      this.renderCodes(data.top_codes || []);
      this.renderTaxpayers(data.top_taxpayers || []);
      this.renderRecent(data.recent || []);
      const refreshed = document.querySelector("#efris-refreshed");
      if (refreshed) refreshed.textContent = when(data.summary?.refreshed_at);
      this.hasRenderedData = true;
    } catch (error) {
      if (this.destroyed) return;
      if (!this.hasRenderedData || initial) this.renderUnavailable(error.message);
      else this.shell.toast(`EFRIS refresh failed: ${error.message}`, true);
    } finally {
      this.loading = false;
    }
  }

  renderUnavailable(message) {
    if (this.timer) window.clearInterval(this.timer);
    this.timer = null;
    this.shell.content.innerHTML = `
      <div class="analytics-unavailable">
        <div class="analytics-unavailable-icon">!</div>
        <p class="eyebrow">Analytics unavailable</p>
        <h2>EFRIS error data cannot be loaded right now</h2>
        <p>${escapeHtml(message)}</p>
        <p class="muted">The source transaction screens remain independent of this analytical page.</p>
        <button class="btn btn-primary" id="efris-retry">Retry</button>
      </div>`;
    document.querySelector("#efris-retry").onclick = () => this.render();
  }

  renderKpis(s) {
    const items = [
      ["ERROR EVENTS", number.format(Number(s.error_events || 0)), "Captured error rows"],
      ["AFFECTED INVOICES", number.format(Number(s.affected_invoices || 0)), "Distinct seller references"],
      ["TAXPAYERS", number.format(Number(s.affected_taxpayers || 0)), "Distinct TINs"],
      ["DEVICES", number.format(Number(s.affected_devices || 0)), "Distinct EFRIS devices"],
      ["UGX GROSS AMOUNT", `UGX ${compact.format(Number(s.ugx_gross_amount || 0))}`, money.format(Number(s.ugx_gross_amount || 0))],
      ["UGX TAX AMOUNT", `UGX ${compact.format(Number(s.ugx_tax_amount || 0))}`, money.format(Number(s.ugx_tax_amount || 0))],
    ];
    document.querySelector("#efris-kpis").innerHTML = items.map(([label,value,note], index) => `
      <div class="dashboard-kpi-card${index >= 4 ? " efris-money-card" : ""}">
        <div class="dashboard-kpi-accent"></div>
        <span class="dashboard-kpi-label">${label}</span>
        <strong class="dashboard-kpi-value">${escapeHtml(value)}</strong>
        <small>${escapeHtml(note)}</small>
      </div>`).join("");
  }

  renderTrend(rows) {
    const target = document.querySelector("#efris-trend");
    target.classList.remove("loading");
    if (!rows.length) { target.innerHTML = `<div class="empty">No EFRIS error activity in this time range.</div>`; return; }
    const data = rows.slice(-40);
    const max = Math.max(...data.map(row => Number(row.error_events || 0)), 1);
    const width = 780, height = 250, padX = 28, padY = 28;
    const chartHeight = height - (padY * 2);
    const gap = 5;
    const barWidth = Math.max(4, ((width - padX * 2) / data.length) - gap);
    const bars = data.map((row, index) => {
      const count = Number(row.error_events || 0);
      const h = Math.max(4, (count / max) * chartHeight);
      const x = padX + index * (barWidth + gap);
      const y = height - padY - h;
      const label = when(row.bucket);
      return `<rect x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="3" class="efris-error-bar"><title>${escapeHtml(label)}: ${count} errors</title></rect>`;
    }).join("");
    target.innerHTML = `<svg class="efris-trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="EFRIS error events over time"><line x1="${padX}" y1="${height-padY}" x2="${width-padX}" y2="${height-padY}" class="efris-axis"></line>${bars}</svg>`;
  }

  renderCodes(rows) {
    const target = document.querySelector("#efris-codes");
    target.classList.remove("loading");
    if (!rows.length) { target.innerHTML = `<div class="empty">No error codes in this time range.</div>`; return; }
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table"><thead><tr><th>Code</th><th>Events</th><th>Invoices</th><th>Taxpayers</th></tr></thead><tbody>${rows.map(row => `<tr><td><span class="efris-code-badge">${escapeHtml(row.return_code)}</span></td><td>${number.format(Number(row.occurrences || 0))}</td><td>${number.format(Number(row.invoices || 0))}</td><td>${number.format(Number(row.taxpayers || 0))}</td></tr>`).join("")}</tbody></table></div>`;
  }

  renderTaxpayers(rows) {
    const target = document.querySelector("#efris-taxpayers");
    target.classList.remove("loading");
    if (!rows.length) { target.innerHTML = `<div class="empty">No affected taxpayers in this time range.</div>`; return; }
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table"><thead><tr><th>TIN</th><th>Errors</th><th>Invoices</th><th>Devices</th></tr></thead><tbody>${rows.map(row => `<tr><td><strong>${escapeHtml(row.tin)}</strong></td><td>${number.format(Number(row.error_events || 0))}</td><td>${number.format(Number(row.invoices || 0))}</td><td>${number.format(Number(row.devices || 0))}</td></tr>`).join("")}</tbody></table></div>`;
  }

  renderRecent(rows) {
    const target = document.querySelector("#efris-recent");
    target.classList.remove("loading");
    if (!rows.length) { target.innerHTML = `<div class="empty">No recent EFRIS error events.</div>`; return; }
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table efris-recent-table"><thead><tr><th>Time</th><th>TIN / Device</th><th>Seller Reference</th><th>Code</th><th>Message</th><th>Gross</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(when(row.create_date))}</td><td><strong>${escapeHtml(row.tin)}</strong><br><span class="muted">${escapeHtml(row.device_no)}</span></td><td>${escapeHtml(row.seller_reference_no)}</td><td><span class="efris-code-badge">${escapeHtml(row.return_code)}</span></td><td class="efris-message">${escapeHtml(row.return_msg || "—")}</td><td class="money">${escapeHtml(row.currency || "")} ${number.format(Number(row.gross_amount || 0))}</td></tr>`).join("")}</tbody></table></div>`;
  }
}
