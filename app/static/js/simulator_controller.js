import { api } from "./api.js";
import { SimulatorPage as SimulatorView } from "./simulator.js";

const LIVE_STATES = new Set(["starting", "running", "paused", "draining"]);

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
}
