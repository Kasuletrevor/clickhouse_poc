# EFRIS Simulator Control Room Implementation Status

Implementation branch: `feature/efris-simulator-control-room`
Base design branch: `feature/efris-error-monitor`

## Implemented

- Shared exact-count EFRIS workload engine.
- Run-scoped source IDs and traceable source prefix.
- Atomic Linux run registry with single-active-run locking.
- Detached worker process that writes Oracle only.
- Pause/Resume/Stop commands and stale-worker detection.
- Stop requests are preserved even while the detached worker is still starting.
- Exact Oracle/ClickHouse reconciliation and CDC latency metrics.
- Oracle/Debezium/Kafka/ClickHouse health checks.
- FastAPI start/status/history/events/pause/resume/stop API.
- Refresh-safe, visibility-aware Simulator Control Room UI.
- Idle configuration is preserved during background polling; another browser's live run takes precedence and is surfaced automatically.
- Live reconciliation strip, pipeline health, run KPIs, latency, event journey and history.
- Structured duplicate-start UX.
- Shared CLI refactored to exact finite event counts.
- Runtime state and environment documentation.
- Focused simulator tests.

## Local verification performed before host rollout

A reconstructed local workspace containing the implementation modules was checked with:

```bash
python -m pytest -q
python -m compileall -q app scripts
node --check app/static/js/api.js
node --check app/static/js/app.js
node --check app/static/js/simulator.js
node --check app/static/js/simulator_controller.js
```

Observed focused test result:

```text
17 passed
```

Two focused browser-lifecycle checks were also run under Node with stubbed status responses:

```text
idle-form-preservation: PASS
cross-browser-active-run-detection: PASS
```

The real RHEL host still needs full-repository tests and runtime verification against Oracle, Debezium, Kafka and ClickHouse before the Control Room is declared operationally complete.
