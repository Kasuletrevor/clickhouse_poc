import { api } from "./api.js";

const money = new Intl.NumberFormat("en-UG", {style:"currency", currency:"UGX", maximumFractionDigits:0});
const when = (value) => value ? new Date(value).toLocaleString() : "—";
const statusBadge = (status) => `<span class="badge badge-${status.toLowerCase()}">${status}</span>`;

export class PaymentsPage {
  constructor(shell) { this.shell = shell; }

  async render() {
    this.shell.content.innerHTML = `
      <div class="page-head"><div><h2>Payment Management</h2><p>Record and manage source-system payments.</p></div><button class="btn btn-primary" id="new-payment">+ New Payment</button></div>
      <div class="kpi-grid" id="payment-kpis"></div>
      <div class="panel">
        <div class="toolbar"><div class="search"><input class="input" id="payment-search" placeholder="Search payment ID, TIN or taxpayer..."></div><div style="width:170px"><select class="select" id="payment-status"><option value="">All statuses</option><option>PENDING</option><option>SUCCESSFUL</option><option>REVERSED</option></select></div><button class="btn" id="payment-refresh">Refresh</button></div>
        <div id="payments-body" class="loading">Loading payments…</div>
      </div>`;
    document.querySelector("#new-payment").onclick = () => this.openCreate();
    document.querySelector("#payment-refresh").onclick = () => this.load();
    document.querySelector("#payment-status").onchange = () => this.load();
    document.querySelector("#payment-search").addEventListener("keydown", e => { if (e.key === "Enter") this.load(); });
    await this.load();
  }

  async load() {
    const body = document.querySelector("#payments-body");
    body.innerHTML = `<div class="loading">Loading payments…</div>`;
    const search = document.querySelector("#payment-search")?.value.trim() || "";
    const status = document.querySelector("#payment-status")?.value || "";
    const params = new URLSearchParams(); if (search) params.set("search", search); if (status) params.set("status", status);
    try {
      const data = await api(`/api/payments?${params}`);
      this.renderKpis(data.summary);
      if (!data.items.length) { body.innerHTML = `<div class="empty">No payments match the current filters.</div>`; return; }
      body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Payment ID</th><th>Taxpayer</th><th>Amount</th><th>Status</th><th>Payment time</th><th>Station</th><th></th></tr></thead><tbody>${data.items.map(p => `<tr><td><button class="link-btn" data-id="${p.payment_id}">${p.payment_id}</button></td><td><strong>${p.taxpayer_id}</strong><br><span class="muted">${p.taxpayer_name || ""}</span></td><td class="money">${money.format(Number(p.amount))}</td><td>${statusBadge(p.status)}</td><td>${when(p.payment_time)}</td><td>${p.station_name || "—"}</td><td><button class="btn detail-btn" data-id="${p.payment_id}">View</button></td></tr>`).join("")}</tbody></table></div>`;
      body.querySelectorAll("[data-id]").forEach(el => el.onclick = () => this.openDetail(el.dataset.id));
    } catch (error) {
      body.innerHTML = `<div class="empty"><strong>Source system unavailable</strong><p>${error.message}</p></div>`;
      this.shell.toast(error.message, true);
    }
  }

  renderKpis(s) {
    document.querySelector("#payment-kpis").innerHTML = `
      <div class="kpi-card"><span>PAYMENTS TODAY</span><strong>${s.payments_today}</strong><small>${money.format(Number(s.amount_today || 0))} total</small></div>
      <div class="kpi-card"><span>SUCCESSFUL</span><strong>${s.successful}</strong><small>Completed transactions</small></div>
      <div class="kpi-card"><span>PENDING</span><strong>${s.pending}</strong><small>Awaiting completion</small></div>
      <div class="kpi-card"><span>REVERSED</span><strong>${s.reversed}</strong><small>Reversed transactions</small></div>`;
  }

  openCreate() {
    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">New transaction</p><h3>Create Payment</h3></div><button class="close-btn" data-close>×</button></div>
      <form id="payment-form">
        <div class="field"><label>Payment ID <span class="muted">(optional)</span></label><input class="input" name="payment_id" maxlength="20" placeholder="Generated automatically if blank"></div>
        <div class="field"><label>Taxpayer TIN</label><input class="input" name="taxpayer_id" maxlength="20" required placeholder="TIN001"></div>
        <div class="field"><label>Amount (UGX)</label><input class="input" name="amount" type="number" min="1" step="0.01" required placeholder="810000"></div>
        <div class="field"><label>Status</label><select class="select" name="status"><option>PENDING</option><option>SUCCESSFUL</option><option>REVERSED</option></select></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Create Payment</button></div>
      </form>`);
    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
    document.querySelector("#payment-form").onsubmit = async e => {
      e.preventDefault(); const form = new FormData(e.target); const submit = e.target.querySelector("button[type=submit]"); submit.disabled = true; submit.textContent = "Creating…";
      try {
        const payload = Object.fromEntries(form.entries()); if (!payload.payment_id) payload.payment_id = null;
        const payment = await api("/api/payments", {method:"POST", body:JSON.stringify(payload)});
        this.shell.closeDrawer(); this.shell.toast(`Payment ${payment.payment_id} created successfully.`); await this.load();
      } catch (error) { this.shell.toast(error.message, true); submit.disabled = false; submit.textContent = "Create Payment"; }
    };
  }

  async openDetail(id) {
    try {
      const p = await api(`/api/payments/${encodeURIComponent(id)}`);
      const actions = p.status === "PENDING" ? `<button class="btn btn-success" data-status="SUCCESSFUL">Mark Successful</button><button class="btn btn-danger" data-status="REVERSED">Reverse Payment</button>` : p.status === "SUCCESSFUL" ? `<button class="btn btn-danger" data-status="REVERSED">Reverse Payment</button>` : `<span class="muted">Reversed payments are terminal.</span>`;
      this.shell.openDrawer(`<div class="drawer-head"><div><p class="eyebrow">Payment detail</p><h3>${p.payment_id} &nbsp; ${statusBadge(p.status)}</h3></div><button class="close-btn" data-close>×</button></div><div class="detail-grid"><div class="detail"><span>Taxpayer</span><strong>${p.taxpayer_id}</strong><small>${p.taxpayer_name || ""}</small></div><div class="detail"><span>Amount</span><strong>${money.format(Number(p.amount))}</strong></div><div class="detail"><span>Station</span><strong>${p.station_name || "—"}</strong><small>${p.station_id || ""}</small></div><div class="detail"><span>Payment Time</span><strong>${when(p.payment_time)}</strong></div><div class="detail"><span>Last Updated</span><strong>${when(p.updated_at)}</strong></div></div><div class="status-actions">${actions}</div>`);
      document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
      document.querySelectorAll("[data-status]").forEach(el => el.onclick = () => this.changeStatus(id, el.dataset.status));
    } catch (error) { this.shell.toast(error.message, true); }
  }

  async changeStatus(id, status) {
    try { const p = await api(`/api/payments/${encodeURIComponent(id)}/status`, {method:"POST", body:JSON.stringify({status})}); this.shell.toast(`${p.payment_id} updated to ${p.status}.`); this.shell.closeDrawer(); await this.load(); }
    catch (error) { this.shell.toast(error.message, true); }
  }
}
