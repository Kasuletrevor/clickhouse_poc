import { api } from "./api.js";

const when = (value) => value ? new Date(value).toLocaleString() : "—";
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

export class TaxpayersPage {
  constructor(shell) {
    this.shell = shell;
    this.stations = [];
  }

  async render() {
    this.shell.content.innerHTML = `
      <div class="page-head">
        <div><h2>Taxpayer Management</h2><p>Maintain taxpayer master data and station assignments.</p></div>
        <button class="btn btn-primary" id="new-taxpayer">+ New Taxpayer</button>
      </div>
      <div class="kpi-grid" id="taxpayer-kpis"></div>
      <div class="panel">
        <div class="toolbar">
          <div class="search"><input class="input" id="taxpayer-search" placeholder="Search TIN or taxpayer name..."></div>
          <div style="width:170px"><input class="input" id="taxpayer-type" placeholder="Taxpayer type"></div>
          <div style="width:210px"><select class="select" id="taxpayer-station"><option value="">All stations</option></select></div>
          <button class="btn" id="taxpayer-refresh">Refresh</button>
        </div>
        <div id="taxpayers-body" class="loading">Loading taxpayers…</div>
      </div>`;

    document.querySelector("#new-taxpayer").onclick = () => this.openCreate();
    document.querySelector("#taxpayer-refresh").onclick = () => this.load();
    document.querySelector("#taxpayer-station").onchange = () => this.load();
    document.querySelector("#taxpayer-type").addEventListener("keydown", e => { if (e.key === "Enter") this.load(); });
    document.querySelector("#taxpayer-search").addEventListener("keydown", e => { if (e.key === "Enter") this.load(); });

    await this.loadStations();
    await this.load();
  }

  async loadStations() {
    try {
      this.stations = await api("/api/taxpayers/station-options");
      const filter = document.querySelector("#taxpayer-station");
      if (filter) {
        filter.innerHTML = `<option value="">All stations</option>${this.stationOptions()}`;
      }
    } catch (error) {
      this.stations = [];
      this.shell.toast(error.message, true);
    }
  }

  stationOptions(selected = "") {
    return this.stations.map(station => `
      <option value="${escapeHtml(station.station_id)}" ${station.station_id === selected ? "selected" : ""}>
        ${escapeHtml(station.station_name)} (${escapeHtml(station.station_id)})
      </option>`).join("");
  }

  async load() {
    const body = document.querySelector("#taxpayers-body");
    if (!body) return;
    body.innerHTML = `<div class="loading">Loading taxpayers…</div>`;

    const params = new URLSearchParams();
    const search = document.querySelector("#taxpayer-search")?.value.trim() || "";
    const type = document.querySelector("#taxpayer-type")?.value.trim() || "";
    const station = document.querySelector("#taxpayer-station")?.value || "";
    if (search) params.set("search", search);
    if (type) params.set("type", type);
    if (station) params.set("station_id", station);

    try {
      const data = await api(`/api/taxpayers?${params}`);
      this.renderKpis(data.summary);
      if (!data.items.length) {
        body.innerHTML = `<div class="empty">No taxpayers match the current filters.</div>`;
        return;
      }

      body.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>TIN</th><th>Taxpayer</th><th>Type</th><th>Station</th><th>Last updated</th><th></th></tr></thead>
        <tbody>${data.items.map(t => `<tr>
          <td><button class="link-btn" data-id="${escapeHtml(t.taxpayer_id)}">${escapeHtml(t.taxpayer_id)}</button></td>
          <td><strong>${escapeHtml(t.taxpayer_name)}</strong></td>
          <td>${escapeHtml(t.taxpayer_type)}</td>
          <td><strong>${escapeHtml(t.station_name || "—")}</strong><br><span class="muted">${escapeHtml(t.station_id || "")}</span></td>
          <td>${when(t.updated_at)}</td>
          <td><button class="btn detail-btn" data-id="${escapeHtml(t.taxpayer_id)}">View</button></td>
        </tr>`).join("")}</tbody>
      </table></div>`;

      body.querySelectorAll("[data-id]").forEach(el => el.onclick = () => this.openDetail(el.dataset.id));
    } catch (error) {
      body.innerHTML = `<div class="empty"><strong>Source system unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
      this.shell.toast(error.message, true);
    }
  }

  renderKpis(summary) {
    document.querySelector("#taxpayer-kpis").innerHTML = `
      <div class="kpi-card"><span>TOTAL TAXPAYERS</span><strong>${summary.total_taxpayers}</strong><small>Source master records</small></div>
      <div class="kpi-card"><span>COMPANIES</span><strong>${summary.companies}</strong><small>Company taxpayers</small></div>
      <div class="kpi-card"><span>OTHER TYPES</span><strong>${summary.other_types}</strong><small>Non-company taxpayers</small></div>
      <div class="kpi-card"><span>STATIONS REPRESENTED</span><strong>${summary.stations_represented}</strong><small>Current assignments</small></div>`;
  }

  async openCreate() {
    if (!this.stations.length) await this.loadStations();
    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">Master data</p><h3>Create Taxpayer</h3></div><button class="close-btn" data-close>×</button></div>
      <form id="taxpayer-form">
        <div class="field"><label>Taxpayer TIN</label><input class="input" name="taxpayer_id" maxlength="30" required placeholder="TIN010"></div>
        <div class="field"><label>Taxpayer Name</label><input class="input" name="taxpayer_name" maxlength="200" required placeholder="Example Traders Ltd"></div>
        <div class="field"><label>Taxpayer Type</label><input class="input" name="taxpayer_type" maxlength="50" required placeholder="COMPANY"></div>
        <div class="field"><label>Station</label><select class="select" name="station_id" required><option value="">Select station</option>${this.stationOptions()}</select></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Create Taxpayer</button></div>
      </form>`);

    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
    document.querySelector("#taxpayer-form").onsubmit = async e => {
      e.preventDefault();
      const submit = e.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "Creating…";
      try {
        const payload = Object.fromEntries(new FormData(e.target).entries());
        const taxpayer = await api("/api/taxpayers", {method:"POST", body:JSON.stringify(payload)});
        this.shell.closeDrawer();
        this.shell.toast(`Taxpayer ${taxpayer.taxpayer_id} created successfully.`);
        await this.load();
      } catch (error) {
        this.shell.toast(error.message, true);
        submit.disabled = false;
        submit.textContent = "Create Taxpayer";
      }
    };
  }

  async openDetail(id) {
    try {
      const taxpayer = await api(`/api/taxpayers/${encodeURIComponent(id)}`);
      this.shell.openDrawer(`
        <div class="drawer-head"><div><p class="eyebrow">Taxpayer detail</p><h3>${escapeHtml(taxpayer.taxpayer_id)}</h3></div><button class="close-btn" data-close>×</button></div>
        <div class="detail-grid">
          <div class="detail"><span>Taxpayer Name</span><strong>${escapeHtml(taxpayer.taxpayer_name)}</strong></div>
          <div class="detail"><span>Type</span><strong>${escapeHtml(taxpayer.taxpayer_type)}</strong></div>
          <div class="detail"><span>Station</span><strong>${escapeHtml(taxpayer.station_name || "—")}</strong><small>${escapeHtml(taxpayer.station_id || "")}</small></div>
          <div class="detail"><span>Last Updated</span><strong>${when(taxpayer.updated_at)}</strong></div>
        </div>
        <div class="status-actions"><button class="btn btn-primary" id="edit-taxpayer">Edit Taxpayer</button></div>`);
      document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
      document.querySelector("#edit-taxpayer").onclick = () => this.openEdit(taxpayer);
    } catch (error) {
      this.shell.toast(error.message, true);
    }
  }

  async openEdit(taxpayer) {
    if (!this.stations.length) await this.loadStations();
    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">Master data</p><h3>Edit ${escapeHtml(taxpayer.taxpayer_id)}</h3></div><button class="close-btn" data-close>×</button></div>
      <form id="taxpayer-edit-form">
        <div class="field"><label>Taxpayer Name</label><input class="input" name="taxpayer_name" maxlength="200" required value="${escapeHtml(taxpayer.taxpayer_name)}"></div>
        <div class="field"><label>Taxpayer Type</label><input class="input" name="taxpayer_type" maxlength="50" required value="${escapeHtml(taxpayer.taxpayer_type)}"></div>
        <div class="field"><label>Station</label><select class="select" name="station_id" required>${this.stationOptions(taxpayer.station_id)}</select></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Save Changes</button></div>
      </form>`);

    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
    document.querySelector("#taxpayer-edit-form").onsubmit = async e => {
      e.preventDefault();
      const submit = e.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "Saving…";
      try {
        const payload = Object.fromEntries(new FormData(e.target).entries());
        const updated = await api(`/api/taxpayers/${encodeURIComponent(taxpayer.taxpayer_id)}`, {method:"PUT", body:JSON.stringify(payload)});
        this.shell.closeDrawer();
        this.shell.toast(`${updated.taxpayer_id} updated successfully.`);
        await this.load();
      } catch (error) {
        this.shell.toast(error.message, true);
        submit.disabled = false;
        submit.textContent = "Save Changes";
      }
    };
  }
}
