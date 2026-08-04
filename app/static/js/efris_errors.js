import { api } from "./api.js";

const number = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const compact = new Intl.NumberFormat("en-UG", {notation: "compact", maximumFractionDigits: 2});
const money = new Intl.NumberFormat("en-UG", {style: "currency", currency: "UGX", maximumFractionDigits: 0});
const when = (value) => value ? new Date(value).toLocaleString("en-UG", {dateStyle:"medium", timeStyle:"short"}) : "—";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

const COMMON_ERRORS = {
  "1600": "Inventory shortage",
  "3077": "Buyer TIN is required and cannot be empty",
  "2249": "Buyer TIN does not exist",
  "2253": "Duplicate seller reference number",
  "2785": "Tax amount does not match expected tax amount",
  "1332": "Tax rate does not match configured tax rate",
  "3083": "Buyer is not allowed for B2G transaction",
};

export class EfrisErrorsPage {
  constructor(shell) {
    this.shell = shell;
    this.timer = null;
    this.loading = false;
    this.destroyed = false;
    this.hasRenderedData = false;
    this.minutes = 60;
    this.taxpayers = [];
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
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
          <button class="btn btn-primary" id="new-efris-error">+ New Error Event</button>
          <select id="efris-range" class="select" style="width:auto;min-width:160px" aria-label="EFRIS time range">
            <option value="15">Last 15 minutes</option>
            <option value="60" selected>Last 1 hour</option>
            <option value="1440">Last 24 hours</option>
            <option value="10080">Last 7 days</option>
          </select>
          <div class="dashboard-refresh"><span class="environment-dot"></span><span>Last refreshed <strong id="efris-refreshed">Loading…</strong></span></div>
        </div>
      </div>
      <div id="efris-kpis" class="dashboard-kpi-grid">
        ${this.kpiSkeleton("Error Events")}
        ${this.kpiSkeleton("Affected Invoices")}
        ${this.kpiSkeleton("Taxpayers")}
        ${this.kpiSkeleton("Devices")}
        ${this.kpiSkeleton("UGX Gross Amount")}
        ${this.kpiSkeleton("UGX Tax Amount")}
      </div>
      <div class="dashboard-chart-grid">
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

    document.querySelector("#new-efris-error").onclick = () => this.openCreate();
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

  async loadTaxpayers() {
    const data = await api("/api/taxpayers?limit=200");
    this.taxpayers = data.items || [];
  }

  taxpayerOptions() {
    return this.taxpayers.map(taxpayer => `
      <option value="${escapeHtml(taxpayer.taxpayer_id)}">${escapeHtml(taxpayer.taxpayer_name)} — ${escapeHtml(taxpayer.taxpayer_id)}</option>`).join("");
  }

  async openCreate() {
    try {
      await this.loadTaxpayers();
    } catch (error) {
      this.shell.toast(`Taxpayers could not be loaded: ${error.message}`, true);
      return;
    }

    if (!this.taxpayers.length) {
      this.shell.toast("No taxpayers are available for EFRIS event creation.", true);
      return;
    }

    const codeOptions = Object.entries(COMMON_ERRORS)
      .map(([code, message]) => `<option value="${code}">${code} — ${escapeHtml(message)}</option>`)
      .join("");

    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">Source transaction</p><h3>Create EFRIS Error Event</h3></div><button class="close-btn" data-close>×</button></div>
      <p class="muted">This writes to Oracle only. CDC then carries the committed event through Debezium, Kafka and ClickHouse.</p>
      <form id="efris-error-form">
        <div class="field"><label>Taxpayer</label><select class="select" name="tin" id="efris-tin" required><option value="">Select taxpayer</option>${this.taxpayerOptions()}</select></div>
        <div class="field"><label>EFRIS Device</label><select class="select" name="device_no" id="efris-device" required disabled><option value="">Select taxpayer first</option></select></div>
        <div class="field"><label>Error Code</label><select class="select" name="return_code" id="efris-code" required><option value="">Select error code</option>${codeOptions}</select></div>
        <div class="field"><label>Error Message</label><input class="input" name="return_msg" id="efris-message" maxlength="256" required placeholder="EFRIS return message"></div>
        <div class="field"><label>Seller Reference <span class="muted">(optional)</span></label><input class="input" name="seller_reference_no" maxlength="50" placeholder="Generated automatically if blank"></div>
        <div class="detail-grid">
          <div class="field"><label>Gross Amount</label><input class="input" name="gross_amount" type="number" min="0.01" step="0.01" required placeholder="850000"></div>
          <div class="field"><label>Tax Amount</label><input class="input" name="tax_amount" type="number" min="0" step="0.01" required placeholder="129661.02"></div>
        </div>
        <div class="field"><label>Currency</label><select class="select" name="currency"><option value="UGX">UGX</option><option value="USD">USD</option></select></div>
        <div class="field"><label>Item Description <span class="muted">(optional)</span></label><input class="input" name="item_description" maxlength="2000" placeholder="POC ELECTRONICS"></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Create Error Event</button></div>
      </form>`);

    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());

    const tinSelect = document.querySelector("#efris-tin");
    const deviceSelect = document.querySelector("#efris-device");
    const codeSelect = document.querySelector("#efris-code");
    const messageInput = document.querySelector("#efris-message");

    tinSelect.onchange = async () => {
      const tin = tinSelect.value;
      deviceSelect.disabled = true;
      deviceSelect.innerHTML = `<option value="">Loading devices…</option>`;
      if (!tin) {
        deviceSelect.innerHTML = `<option value="">Select taxpayer first</option>`;
        return;
      }
      try {
        const devices = await api(`/api/efris-errors/devices?tin=${encodeURIComponent(tin)}`);
        if (!devices.length) {
          deviceSelect.innerHTML = `<option value="">No EFRIS devices registered</option>`;
          return;
        }
        deviceSelect.innerHTML = `<option value="">Select device</option>${devices.map(d => `<option value="${escapeHtml(d.device_no)}">${escapeHtml(d.device_no)}${d.device_type ? ` — ${escapeHtml(d.device_type)}` : ""}</option>`).join("")}`;
        deviceSelect.disabled = false;
      } catch (error) {
        deviceSelect.innerHTML = `<option value="">Unable to load devices</option>`;
        this.shell.toast(error.message, true);
      }
    };

    codeSelect.onchange = () => {
      if (COMMON_ERRORS[codeSelect.value]) messageInput.value = COMMON_ERRORS[codeSelect.value];
    };

    document.querySelector("#efris-error-form").onsubmit = async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const submit = event.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "Creating…";
      try {
        const payload = Object.fromEntries(form.entries());
        if (!payload.seller_reference_no) payload.seller_reference_no = null;
        if (!payload.item_description) payload.item_description = null;
        const created = await api("/api/efris-errors", {method:"POST", body:JSON.stringify(payload)});
        this.shell.closeDrawer();
        this.shell.toast(`EFRIS error ${created.error_event_id} committed to Oracle. Waiting for CDC ingestion.`);
        window.setTimeout(() => this.refresh(false), 3000);
      } catch (error) {
        this.shell.toast(error.message, true);
        submit.disabled = false;
        submit.textContent = "Create Error Event";
      }
    };
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
      ["ERROR EVENTS", number.format(Number(s.error_events || 0)), "Captured error rows", ""],
      ["AFFECTED INVOICES", number.format(Number(s.affected_invoices || 0)), "Distinct seller references", ""],
      ["TAXPAYERS", number.format(Number(s.affected_taxpayers || 0)), "Distinct TINs", ""],
      ["DEVICES", number.format(Number(s.affected_devices || 0)), "Distinct EFRIS devices", ""],
      ["UGX GROSS AMOUNT", `UGX ${compact.format(Number(s.ugx_gross_amount || 0))}`, money.format(Number(s.ugx_gross_amount || 0)), " dashboard-kpi-money"],
      ["UGX TAX AMOUNT", `UGX ${compact.format(Number(s.ugx_tax_amount || 0))}`, money.format(Number(s.ugx_tax_amount || 0)), " dashboard-kpi-money"],
    ];
    document.querySelector("#efris-kpis").innerHTML = items.map(([label,value,note,extra]) => `
      <div class="dashboard-kpi-card${extra}">
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
      return `<rect x="${x}" y="${y}" width="${barWidth}" height="${h}" rx="3" fill="var(--ura-yellow)"><title>${escapeHtml(label)}: ${count} errors</title></rect>`;
    }).join("");
    target.innerHTML = `<svg style="display:block;width:100%;height:auto;min-height:240px" viewBox="0 0 ${width} ${height}" role="img" aria-label="EFRIS error events over time"><line x1="${padX}" y1="${height-padY}" x2="${width-padX}" y2="${height-padY}" stroke="var(--border)" stroke-width="1"></line>${bars}</svg>`;
  }

  renderCodes(rows) {
    const target = document.querySelector("#efris-codes");
    target.classList.remove("loading");
    if (!rows.length) { target.innerHTML = `<div class="empty">No error codes in this time range.</div>`; return; }
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table"><thead><tr><th>Code</th><th>Events</th><th>Invoices</th><th>Taxpayers</th></tr></thead><tbody>${rows.map(row => `<tr><td><span class="badge badge-reversed">${escapeHtml(row.return_code)}</span></td><td>${number.format(Number(row.occurrences || 0))}</td><td>${number.format(Number(row.invoices || 0))}</td><td>${number.format(Number(row.taxpayers || 0))}</td></tr>`).join("")}</tbody></table></div>`;
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
    target.innerHTML = `<div class="table-wrap"><table class="dashboard-table"><thead><tr><th>Time</th><th>TIN / Device</th><th>Seller Reference</th><th>Code</th><th>Message</th><th>Gross</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHtml(when(row.create_date))}</td><td><strong>${escapeHtml(row.tin)}</strong><br><span class="muted">${escapeHtml(row.device_no)}</span></td><td>${escapeHtml(row.seller_reference_no)}</td><td><span class="badge badge-reversed">${escapeHtml(row.return_code)}</span></td><td style="min-width:220px">${escapeHtml(row.return_msg || "—")}</td><td class="money">${escapeHtml(row.currency || "")} ${number.format(Number(row.gross_amount || 0))}</td></tr>`).join("")}</tbody></table></div>`;
  }
}
