# Implementation Plan — Internal Transaction Application

## Goal

Build the approved FastAPI + HTML/CSS/vanilla JavaScript internal transactional application on top of the already-working CDC pipeline.

Do not rebuild the CDC stack. Build vertically and verify each slice end-to-end.

---

## Phase 0 — Repository inspection and safety

Before writing application code:

1. Inspect `compose.yaml`.
2. Inspect `simulator/oracle_simulator.py` and `simulator/run_load.py`.
3. Confirm ignored runtime/secret paths remain ignored.
4. Confirm no real credentials are committed.
5. Confirm current Docker service names and ports.
6. Confirm existing ClickHouse objects and current Oracle schema.
7. Read `docs/cdc_internal_transaction_app_design_spec.md` completely.

Output of this phase should be a short implementation note describing any differences between repository reality and the design document.

---

## Phase 1 — Application shell

Create the base FastAPI application and frontend shell.

Target structure:

```text
app/
├── main.py
├── config.py
├── oracle.py
├── clickhouse.py
├── routes/
├── services/
├── schemas/
├── templates/
│   └── index.html
└── static/
    ├── css/
    └── js/
```

Deliver:

- FastAPI startup
- static assets
- single application shell
- persistent navy sidebar
- header
- content area
- SPA-style navigation
- reusable drawer
- reusable modal
- toast system
- loading/error component patterns

Do not implement authentication.

### Acceptance

- `uvicorn app.main:app --host 0.0.0.0 --port 8000` starts successfully.
- `/` renders the full shell.
- sidebar navigation changes content without full browser reloads.
- no secrets are exposed to the browser.

---

## Phase 2 — Payments vertical slice

This is the first full business slice and the most important initial milestone.

### Backend

Implement:

```text
GET  /api/payments
GET  /api/payments/{id}
POST /api/payments
POST /api/payments/{id}/status
```

Use Oracle only.

Business state rules:

```text
PENDING → SUCCESSFUL
PENDING → REVERSED
SUCCESSFUL → REVERSED
REVERSED → terminal
```

Validate:

- positive amount
- taxpayer exists
- taxpayer is active
- station exists/active
- payment ID unique
- valid status transition

Translate Oracle errors to safe API errors.

### Frontend

Deliver:

- payment KPIs
- search
- status filter
- date filter
- payments table
- New Payment drawer
- Payment Detail drawer
- Mark Successful action
- Reverse action
- success/error toasts
- loading states

### Acceptance

Create a payment from the browser and prove:

```text
Browser → FastAPI → Oracle COMMIT → Debezium → Kafka → ClickHouse
```

The app must not call Kafka or ClickHouse during the source write.

---

## Phase 3 — Taxpayers

Implement:

```text
GET    /api/taxpayers
GET    /api/taxpayers/{tin}
POST   /api/taxpayers
PUT    /api/taxpayers/{tin}
POST   /api/taxpayers/{tin}/deactivate
POST   /api/taxpayers/{tin}/activate
```

Features:

- list/search/filter
- create
- edit
- station reassignment
- deactivate/reactivate
- friendly validation

Source changes must update `UPDATED_AT`.

### Acceptance

Move a taxpayer to a different station through the app and verify downstream ClickHouse history preserves the former assignment interval.

---

## Phase 4 — Stations

Implement:

```text
GET    /api/stations
GET    /api/stations/{id}
POST   /api/stations
PUT    /api/stations/{id}
POST   /api/stations/{id}/deactivate
POST   /api/stations/{id}/activate
```

Before deactivation, count active taxpayers assigned to the station.

Return a friendly `409` if the station is still in use.

Do not expose raw FK errors.

---

## Phase 5 — Dashboard

Read ClickHouse only.

Suggested endpoints:

```text
GET /api/dashboard/summary
GET /api/dashboard/payments-by-station
GET /api/dashboard/status-summary
GET /api/dashboard/recent-activity
```

Suggested KPIs:

```text
Total Taxpayers
Active Stations
Payments Today
Amount Collected Today
```

Keep CDC terminology out of this page.

### Failure behavior

If ClickHouse is unavailable, show a clear analytical-service warning while operational screens remain usable.

---

## Phase 6 — Event Monitor

Build an engineering/audit view over ClickHouse raw history.

Features:

- recent events
- entity filter
- operation filter
- ID search
- LIVE polling toggle
- event detail drawer

Show:

```text
operation
entity ID
SCN
commit SCN
transaction ID
source user
source commit time
Kafka topic/partition/offset
ClickHouse ingestion time
latency
```

For updates, derive before/after values from adjacent versions where reliable.

Do not require users to read raw Debezium JSON.

---

## Phase 7 — Pipeline Health

Implement:

```text
GET /api/pipeline/health
```

Check independently:

- Oracle
- Debezium connector/task state
- Kafka lag
- ClickHouse

Return partial results even if one subsystem fails.

Frontend:

```text
Oracle → Debezium → Kafka → ClickHouse
```

with status cards, lag and latest-event information.

Do not add infrastructure mutation controls.

---

## Phase 8 — Simulator control

Reuse/refactor the existing simulator rather than duplicating it.

Endpoints:

```text
POST /api/simulator/start
POST /api/simulator/stop
GET  /api/simulator/status
```

UI:

- start/stop
- transactions per minute
- event mix
- running status
- recent generated activity

The simulator must continue writing only to Oracle.

Prevent duplicate uncontrolled workers.

---

## Phase 9 — Reports

Provide simple operational summaries only.

Examples:

- daily collections
- payments by station
- payments by taxpayer
- payment status summary

Power BI remains the full analytical platform.

---

## Phase 10 — Deployment

Development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Stable deployment:

- systemd service
- automatic restart
- environment file
- journal logging
- documented start/stop/status commands

Test `http://10.1.78.38:8000` from the intended demo host before changing network controls.

---

## Testing strategy

### Fast unit/business tests

At minimum:

```text
PENDING → SUCCESSFUL allowed
PENDING → REVERSED allowed
SUCCESSFUL → REVERSED allowed
REVERSED → SUCCESSFUL rejected
negative payment rejected
zero payment rejected
inactive taxpayer rejected
inactive station rejected
station in use cannot deactivate
```

### API tests

Verify:

- status codes
- safe error shape
- no raw database errors
- validation behavior

### End-to-end smoke test

```text
create payment via API
verify Oracle
wait for CDC
verify ClickHouse raw event
verify current fact
verify serving view
```

Keep this separate from fast unit tests.

---

## Branch/PR strategy

Recommended:

```text
main
  └── feature/internal-transaction-app
```

Prefer logically scoped commits.

If practical, review the major vertical slices separately rather than delivering one enormous unreviewable change.

Each PR/review should verify:

```text
[ ] Oracle remains source of truth
[ ] no app write to Kafka
[ ] no app write to ClickHouse
[ ] source writes commit transactionally
[ ] business rules enforced server-side
[ ] secrets absent
[ ] errors translated safely
[ ] SCD2 semantics preserved
[ ] UI matches approved direction
[ ] tests included
```

---

## Definition of done

The POC application is complete when a user can create/update source transactions in the web app, observe them first in Oracle and subsequently through the CDC pipeline into ClickHouse/Power BI, while historical station-at-payment semantics remain correct and analytical subsystem failures do not prevent normal Oracle CRUD.
