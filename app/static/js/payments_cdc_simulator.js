const nf = new Intl.NumberFormat("en-UG", {maximumFractionDigits: 0});

export class PaymentsCdcSimulatorPage {
  constructor(shell) {
    this.shell = shell;
  }

  async render() {
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
        <strong>POC page copy</strong>
        <span>This first pass duplicates the existing Simulator visual language for the payments and taxpayer CDC use case. Controls will be wired to the existing Oracle simulator after the page layout is approved.</span>
      </div>

      <div class="sim-idle-grid">
        <section class="sim-panel sim-config-panel">
          <div class="sim-panel-head">
            <div><p class="eyebrow">Source workload</p><h3>Configure Simulation</h3></div>
            <span class="sim-safe-chip">Oracle source</span>
          </div>
          <form class="sim-config-form" id="payments-cdc-preview-form">
            <label>
              <span>Target rate</span>
              <div class="sim-input-unit"><input class="input" type="number" min="1" value="10"><em>events/min</em></div>
              <small>Creates real source transactions in the Oracle POC database.</small>
            </label>
            <label>
              <span>Duration</span>
              <div class="sim-input-unit"><input class="input" type="number" min="1" value="10"><em>minutes</em></div>
              <small>Duration of the controlled source workload.</small>
            </label>
            <label>
              <span>Taxpayer station movement</span>
              <div class="sim-input-unit"><input class="input" type="number" min="0" max="100" value="5"><em>%</em></div>
              <small>The terminal simulator already mixes payment creation, status updates and taxpayer station changes.</small>
            </label>
            <div class="sim-target-preview">
              <span>Traffic mix</span>
              <strong>80 / 15 / 5</strong>
              <small>Payment create / status update / taxpayer move</small>
            </div>
            <button class="btn btn-primary sim-start-button" type="submit"><span>▶</span> Start Simulation</button>
          </form>
        </section>

        <div class="sim-idle-side">
          <section class="sim-panel">
            <div class="sim-panel-head"><div><p class="eyebrow">Demo scope</p><h3>CDC Use Cases</h3></div></div>
            <div class="sim-pop-grid">
              ${this.scopeCard("PAY", "Payment transactions")}
              ${this.scopeCard("STS", "Payment status updates")}
              ${this.scopeCard("TIN", "Taxpayer station changes")}
              ${this.scopeCard("CDC", "End-to-end streaming")}
            </div>
          </section>
          ${this.healthPanel()}
        </div>
      </div>

      <section class="sim-reconcile-grid" aria-label="CDC movement preview">
        ${this.reconcileCard("SOURCE", "Oracle", 0, "committed", "Waiting for a simulated source transaction", "source")}
        <div class="sim-flight-card"><span class="sim-flow-arrow">→</span><p>IN FLIGHT</p><strong>0</strong><small>Debezium → Kafka</small><span class="sim-flow-arrow right">→</span></div>
        ${this.reconcileCard("DESTINATION", "ClickHouse", 0, "received", "Waiting for CDC delivery", "destination")}
      </section>

      <section class="sim-panel sim-events-panel">
        <div class="sim-panel-head">
          <div><p class="eyebrow">Event journey</p><h3>Live Payment & Taxpayer Events</h3></div>
          <span class="sim-panel-note">Oracle → Debezium → Kafka → ClickHouse</span>
        </div>
        <div class="sim-events-empty">
          <span>⌁</span>
          <strong>Waiting for the first simulated transaction</strong>
          <p>When the simulator is wired, each Oracle payment or taxpayer change will appear here as it moves across the CDC pipeline.</p>
        </div>
      </section>
    </div>`;

    document.querySelector("#payments-cdc-preview-form")?.addEventListener("submit", event => {
      event.preventDefault();
      this.shell.toast("Preview only: simulator controls will be wired after this page layout is approved");
    });

    return this;
  }

  destroy() {}

  scopeCard(code, label) {
    return `<div class="sim-pop-card"><strong>${code}</strong><span>${label}</span></div>`;
  }

  reconcileCard(kicker, name, count, verb, note, cls) {
    return `<div class="sim-reconcile-card ${cls}"><p>${kicker}</p><h3>${name}</h3><strong>${nf.format(Number(count || 0))}</strong><span>${verb}</span><small>${note}</small></div>`;
  }

  healthPanel() {
    const stages = [
      ["Oracle", "Source database ready"],
      ["Debezium", "CDC connector"],
      ["Kafka", "Streaming transport"],
      ["ClickHouse", "Analytics destination"],
    ];
    return `<section class="sim-panel sim-health-panel">
      <div class="sim-panel-head">
        <div><p class="eyebrow">Pipeline</p><h3>CDC Components</h3></div>
        <span class="sim-panel-note">same POC path</span>
      </div>
      <div class="sim-health-grid">
        ${stages.map(([label, detail]) => `<div class="sim-health-card health-unknown"><span class="sim-health-icon">•</span><div><strong>${label}</strong><b>READY</b><small>${detail}</small></div></div>`).join("")}
      </div>
    </section>`;
  }
}
