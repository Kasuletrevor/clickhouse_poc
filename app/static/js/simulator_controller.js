import { api } from "./api.js";
import { SimulatorPage as SimulatorView } from "./simulator.js";

const LIVE_STATES = new Set(["starting", "running", "paused", "draining"]);
const nf = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});
const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

/**
 * Refresh/reconnect lifecycle for the Simulator view.
 *
 * Keeping this controller separate prevents the one-second status poll from
 * rebuilding an idle configuration form while the user is editing it. Active
 * runs always take precedence, so a run started in another browser is surfaced
 * immediately instead of leaving this tab on a stale form.
 */
export class SimulatorPage extends SimulatorView {
  async refresh(initial = false) {
    if (this.loading || this.destroyed) return;
    this.loading = true;
    try {
      const data = await api("/api/simulator/status");
      if (this.destroyed) return;

      const liveRun = data.active && LIVE_STATES.has(data.active.status);
      if (liveRun) {
        const wasConfiguring = this.configureNew;
        this.configureNew = false;
        if (initial) {
          this.shell.toast(`Reconnected to active simulation ${data.active.run_id}`);
        } else if (wasConfiguring) {
          this.shell.toast(`Active simulation ${data.active.run_id} detected; showing the running workload`);
        }
        this.renderRun(data);
        return;
      }

      if (this.configureNew) {
        if (!document.querySelector("#sim-start-form")) this.renderIdle(data, true);
        return;
      }

      if (data.active) {
        this.renderRun(data);
        return;
      }

      // Do not replace a form that is already on screen. This preserves user
      // input and focus while background status polling continues.
      if (initial || !document.querySelector("#sim-start-form")) {
        this.renderIdle(data, false);
      }
    } catch (error) {
      if (!this.destroyed) this.renderUnavailable(error.message);
    } finally {
      this.loading = false;
    }
  }

  renderRun(data) {
    super.renderRun(data);
    const run = data.active;
    if (!run) return;

    if (run.status === "draining" && run.can_close_cdc_gap) {
      const actions = document.querySelector(".sim-run-actions");
      if (actions) {
        actions.innerHTML = `<button class="btn" disabled>CDC is draining…</button><button id="sim-close-gap" class="btn btn-danger">Close with CDC Gap</button>`;
        document.querySelector("#sim-close-gap")?.addEventListener("click", () => this.confirmGap(run));
      }
    }

    if (run.status === "cdc_gap") {
      this.renderCdcGapState(run, data);
    }
  }

  renderCdcGapState(run, data) {
    const hero = document.querySelector(".sim-run-hero");
    const badge = document.querySelector(".sim-status-badge");
    const titleCopy = document.querySelectorAll(".sim-run-title > p");
    const actions = document.querySelector(".sim-run-actions");
    const flight = document.querySelector(".sim-flight-card");

    hero?.classList.remove("tone-neutral", "tone-warning", "tone-success", "tone-info");
    hero?.classList.add("tone-danger");
    if (badge) {
      badge.className = "sim-status-badge tone-danger";
      badge.innerHTML = `<span class="sim-status-dot"></span>CDC GAP`;
    }
    if (titleCopy.length) {
      titleCopy[titleCopy.length - 1].textContent = "Run closed with a CDC delivery gap. Oracle source evidence is preserved; missing downstream events were not recoverable.";
    }
    if (actions) {
      actions.innerHTML = `<button id="sim-new-run" class="btn btn-primary"><span>＋</span> Start New Run</button>`;
      document.querySelector("#sim-new-run")?.addEventListener("click", () => {
        this.configureNew = true;
        this.renderIdle(data, true);
      });
    }
    if (flight) {
      flight.innerHTML = `<span class="sim-flow-arrow">→</span><p>CDC GAP</p><strong>${nf.format(Number(run.gap_events || 0))}</strong><small>committed events were not recovered</small><span class="sim-flow-arrow right">→</span>`;
    }

    if (hero && !document.querySelector("#sim-gap-notice")) {
      hero.insertAdjacentHTML("afterend", `<div id="sim-gap-notice" class="sim-inline-notice"><strong>Delivery gap recorded</strong><span>${nf.format(Number(run.gap_clickhouse_received || run.clickhouse_received || 0))} of ${nf.format(Number(run.gap_oracle_committed || run.oracle_committed || 0))} Oracle commits reached ClickHouse. ${nf.format(Number(run.gap_events || 0))} events are recorded as an unrecovered CDC gap.</span></div>`);
    }
  }

  confirmGap(run) {
    this.shell.openDrawer(`<div class="drawer-head"><div><p class="eyebrow">CDC continuity loss</p><h3>Close Run with CDC Gap?</h3></div><button class="close-btn" data-close>×</button></div>
      <div class="sim-stop-warning"><span>!</span><div><strong>${escapeHtml(run.run_id)}</strong><p>This does not repair or replay missing events. It records the current Oracle-to-ClickHouse shortfall as a permanent CDC gap and closes this run so a new simulation can start.</p></div></div>
      <div class="detail-grid"><div class="detail"><span>Oracle committed</span><strong>${nf.format(run.oracle_committed || 0)}</strong></div><div class="detail"><span>ClickHouse received</span><strong>${nf.format(run.clickhouse_received || 0)}</strong></div><div class="detail"><span>Current shortfall</span><strong>${nf.format(run.in_flight || 0)}</strong></div></div>
      <div class="form-actions"><button class="btn" data-close>Keep Draining</button><button id="confirm-sim-gap" class="btn btn-danger">Close with CDC Gap</button></div>`);
    document.querySelectorAll("[data-close]").forEach(el => el.onclick = () => this.shell.closeDrawer());
    document.querySelector("#confirm-sim-gap").onclick = async () => {
      const button = document.querySelector("#confirm-sim-gap");
      button.disabled = true;
      button.textContent = "Recording gap…";
      try {
        const closed = await api(`/api/simulator/runs/${encodeURIComponent(run.run_id)}/close-gap`, {method:"POST"});
        this.shell.closeDrawer();
        this.shell.toast(`Run closed with CDC gap: ${nf.format(closed.gap_events || 0)} events not recovered`);
        await this.refresh(false);
      } catch (error) {
        this.shell.toast(error.message, true);
        button.disabled = false;
        button.textContent = "Close with CDC Gap";
      }
    };
  }
}
