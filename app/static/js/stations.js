import { api } from "./api.js";

const when = (value) => value ? new Date(value).toLocaleString() : "—";

export class StationsPage {
  constructor(shell) {
    this.shell = shell;
    this.regions = [];
  }

  async render() {
    this.shell.content.innerHTML = `
      <div class="page-head">
        <div><h2>Station Management</h2><p>Maintain station master data used by taxpayers and payments.</p></div>
        <button class="btn btn-primary" id="new-station">+ New Station</button>
      </div>
      <div class="kpi-grid" id="station-kpis"></div>
      <div class="panel">
        <div class="toolbar">
          <div class="search"><input class="input" id="station-search" placeholder="Search station, region or district..."></div>
          <div style="width:180px"><select class="select" id="station-region"><option value="">All regions</option></select></div>
          <button class="btn" id="station-refresh">Refresh</button>
        </div>
        <div id="stations-body" class="loading">Loading stations…</div>
      </div>`;

    document.querySelector("#new-station").onclick = () => this.openCreate();
    document.querySelector("#station-refresh").onclick = () => this.load();
    document.querySelector("#station-region").onchange = () => this.load();
    document.querySelector("#station-search").addEventListener("keydown", e => {
      if (e.key === "Enter") this.load();
    });

    await this.load(true);
  }

  async load(refreshRegions = false) {
    const body = document.querySelector("#stations-body");
    body.innerHTML = `<div class="loading">Loading stations…</div>`;
    const search = document.querySelector("#station-search")?.value.trim() || "";
    const region = document.querySelector("#station-region")?.value || "";
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (region) params.set("region", region);

    try {
      const data = await api(`/api/stations?${params}`);
      this.renderKpis(data.summary);

      if (refreshRegions) {
        this.regions = [...new Set(data.items.map(s => s.region).filter(Boolean))].sort();
        this.renderRegionOptions(region);
      }

      if (!data.items.length) {
        body.innerHTML = `<div class="empty">No stations match the current filters.</div>`;
        return;
      }

      body.innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>Station ID</th><th>Station</th><th>Region</th><th>District</th><th>Taxpayers</th><th>Updated</th><th></th></tr></thead>
        <tbody>${data.items.map(s => `<tr>
          <td><button class="link-btn" data-station="${s.station_id}">${s.station_id}</button></td>
          <td><strong>${s.station_name}</strong></td>
          <td>${s.region || "—"}</td>
          <td>${s.district || "—"}</td>
          <td><strong>${s.taxpayer_count}</strong></td>
          <td>${when(s.updated_at)}</td>
          <td><button class="btn" data-station="${s.station_id}">View</button></td>
        </tr>`).join("")}</tbody>
      </table></div>`;

      body.querySelectorAll("[data-station]").forEach(el => {
        el.onclick = () => this.openDetail(el.dataset.station);
      });
    } catch (error) {
      body.innerHTML = `<div class="empty"><strong>Source system unavailable</strong><p>${error.message}</p></div>`;
      this.shell.toast(error.message, true);
    }
  }

  renderKpis(summary) {
    document.querySelector("#station-kpis").innerHTML = `
      <div class="kpi-card"><span>TOTAL STATIONS</span><strong>${summary.total_stations}</strong><small>Source-system stations</small></div>
      <div class="kpi-card"><span>REGIONS</span><strong>${summary.regions}</strong><small>Regions represented</small></div>
      <div class="kpi-card"><span>DISTRICTS</span><strong>${summary.districts}</strong><small>Districts represented</small></div>
      <div class="kpi-card"><span>ASSIGNED TAXPAYERS</span><strong>${summary.taxpayers_assigned}</strong><small>Current station assignments</small></div>`;
  }

  renderRegionOptions(selected = "") {
    const select = document.querySelector("#station-region");
    select.innerHTML = `<option value="">All regions</option>${this.regions.map(region => `<option value="${region}" ${region === selected ? "selected" : ""}>${region}</option>`).join("")}`;
  }

  openCreate() {
    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">Master data</p><h3>Create Station</h3></div><button class="close-btn" data-close>×</button></div>
      <form id="station-form">
        <div class="field"><label>Station ID</label><input class="input" name="station_id" maxlength="20" required placeholder="ST004"></div>
        <div class="field"><label>Station Name</label><input class="input" name="station_name" maxlength="100" required placeholder="Entebbe"></div>
        <div class="field"><label>Region</label><input class="input" name="region" maxlength="50" required placeholder="CENTRAL"></div>
        <div class="field"><label>District</label><input class="input" name="district" maxlength="50" required placeholder="WAKISO"></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Create Station</button></div>
      </form>`);
    this.bindClose();
    document.querySelector("#station-form").onsubmit = async e => {
      e.preventDefault();
      const submit = e.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "Creating…";
      try {
        const payload = Object.fromEntries(new FormData(e.target).entries());
        const station = await api("/api/stations", {method:"POST", body:JSON.stringify(payload)});
        this.shell.closeDrawer();
        this.shell.toast(`Station ${station.station_id} created successfully.`);
        await this.load(true);
      } catch (error) {
        this.shell.toast(error.message, true);
        submit.disabled = false;
        submit.textContent = "Create Station";
      }
    };
  }

  async openDetail(id) {
    try {
      const s = await api(`/api/stations/${encodeURIComponent(id)}`);
      this.shell.openDrawer(`
        <div class="drawer-head"><div><p class="eyebrow">Station detail</p><h3>${s.station_id}</h3></div><button class="close-btn" data-close>×</button></div>
        <div class="detail-grid">
          <div class="detail"><span>Station Name</span><strong>${s.station_name}</strong></div>
          <div class="detail"><span>Region</span><strong>${s.region || "—"}</strong></div>
          <div class="detail"><span>District</span><strong>${s.district || "—"}</strong></div>
          <div class="detail"><span>Assigned Taxpayers</span><strong>${s.taxpayer_count}</strong></div>
          <div class="detail"><span>Last Updated</span><strong>${when(s.updated_at)}</strong></div>
        </div>
        <div class="status-actions"><button class="btn btn-primary" id="edit-station">Edit Station</button></div>`);
      this.bindClose();
      document.querySelector("#edit-station").onclick = () => this.openEdit(s);
    } catch (error) {
      this.shell.toast(error.message, true);
    }
  }

  openEdit(station) {
    this.shell.openDrawer(`
      <div class="drawer-head"><div><p class="eyebrow">Master data</p><h3>Edit ${station.station_id}</h3></div><button class="close-btn" data-close>×</button></div>
      <form id="station-edit-form">
        <div class="field"><label>Station Name</label><input class="input" name="station_name" maxlength="100" required value="${station.station_name}"></div>
        <div class="field"><label>Region</label><input class="input" name="region" maxlength="50" required value="${station.region || ""}"></div>
        <div class="field"><label>District</label><input class="input" name="district" maxlength="50" required value="${station.district || ""}"></div>
        <div class="form-actions"><button type="button" class="btn" data-close>Cancel</button><button class="btn btn-primary" type="submit">Save Changes</button></div>
      </form>`);
    this.bindClose();
    document.querySelector("#station-edit-form").onsubmit = async e => {
      e.preventDefault();
      const submit = e.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "Saving…";
      try {
        const payload = Object.fromEntries(new FormData(e.target).entries());
        const updated = await api(`/api/stations/${encodeURIComponent(station.station_id)}`, {method:"PUT", body:JSON.stringify(payload)});
        this.shell.toast(`Station ${updated.station_id} updated successfully.`);
        this.shell.closeDrawer();
        await this.load(true);
      } catch (error) {
        this.shell.toast(error.message, true);
        submit.disabled = false;
        submit.textContent = "Save Changes";
      }
    };
  }

  bindClose() {
    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
  }
}
