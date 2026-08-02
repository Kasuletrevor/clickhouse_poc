# CDC Internal Transaction Application — Design & Codex Handoff

**Project:** Oracle → Debezium → Kafka → ClickHouse → Power BI CDC POC  
**Web application:** Trusted internal transactional system  
**Frontend:** HTML + CSS + vanilla JavaScript  
**Backend:** FastAPI  
**Repository root on POC host:** `/home/jkasule/cdc-clickhouse-poc`  
**Status:** CDC backend proven end-to-end; web application is the next layer.

---

## 1. Goal

Build a polished internal transactional web application on top of the existing CDC POC.

The app must look like a real internal business system rather than a CDC demo. Normal users should be able to operate Taxpayers, Stations and Payments without needing to know anything about Kafka, Debezium, SCNs or LogMiner.

Business-facing screens:

- Dashboard
- Taxpayers
- Stations
- Payments
- Reports

Engineering screens:

- Pipeline Health
- Event Monitor
- Simulator

This is a trusted internal POC:

- no login screen
- no JWT
- no role management
- no authentication flow
- direct landing on Dashboard
- no organizational logo

Use a professional navy + yellow/gold visual identity with white/light-gray content surfaces.

---

## 2. Non-negotiable architecture rule

All business writes go to **Oracle only**.

```text
Browser
  ↓
FastAPI
  ↓
Oracle CDC_APP
  ↓
Oracle redo
  ↓
Debezium LogMiner
  ↓
Kafka
  ↓
ClickHouse
  ↓
Power BI
```

The app must never publish business events directly to Kafka and must never write business rows directly to ClickHouse.

### Operational ownership

These screens read/write Oracle:

```text
Taxpayers
Stations
Payments
```

These screens read ClickHouse or infrastructure health data:

```text
Dashboard
Reports
Event Monitor
Pipeline Health
```

A newly committed Oracle payment should appear immediately in the Oracle-backed Payments screen, then appear downstream after CDC propagation.

The propagation delay is expected and useful to demonstrate.

---

## 3. Current schema freeze — important

For the current application phase, the existing `CDC_APP.TAXPAYER` and `CDC_APP.STATION` schemas are considered **frozen** unless the user explicitly approves a later schema change.

Do **not** add:

```text
TAXPAYER.STATUS
STATION.STATUS
```

Do not add other lifecycle fields merely to support the first application milestone.

This decision supersedes any earlier draft language that proposed ACTIVE/INACTIVE columns.

### Consequences for this phase

Taxpayer operations supported now:

```text
list
view
create
edit
station reassignment
```

Station operations supported now:

```text
list
view
create
edit
```

Deferred until a later explicit design decision:

```text
taxpayer deactivate/reactivate
station deactivate/reactivate
hard-delete lifecycle rules
```

Payments may validate:

```text
amount > 0
taxpayer exists
referenced taxpayer station exists
payment ID unique
payment status is valid
payment status transition is valid
```

Payments must **not** validate `taxpayer ACTIVE` or `station ACTIVE`, because those source fields do not currently exist and must not be introduced in this phase.

This schema freeze deliberately reduces risk to the already-proven CDC pipeline while the first web application is being built.

---

## 4. Existing infrastructure

Main host:

```text
datalake-test02
```

Existing services:

```text
poc-oracle
poc-debezium
poc-kafka
poc-kafbat
poc-clickhouse
```

Important ports:

```text
Oracle       1521
Debezium     8083 (localhost-bound)
Kafka        9092 host / kafka:19092 inside Docker network
Kafbat       8080
ClickHouse   8123 HTTP
ClickHouse   9000 native
```

Kafbat is available at:

```text
http://10.1.78.38:8080
```

Corporate proxy:

```text
http://proxy.ura.local:8080
```

Do not redesign host proxy/networking/firewall behavior unless a specific demonstrated requirement exists.

---

## 5. Oracle source model

Database/PDB:

```text
FREE
FREEPDB1
```

Schema:

```text
CDC_APP
```

Use environment variables for credentials.

### STATION

Existing fields:

```text
STATION_ID
STATION_NAME
REGION
DISTRICT
UPDATED_AT
```

Example rows:

```text
ST001  Kampala Central  CENTRAL  Kampala
ST002  Jinja            EASTERN  Jinja
ST003  Nakawa           CENTRAL  Kampala
```

### TAXPAYER

Existing fields:

```text
TAXPAYER_ID
TAXPAYER_NAME
TAXPAYER_TYPE
STATION_ID
UPDATED_AT
```

Example rows:

```text
TIN001  KJT Traders      COMPANY
TIN002  ABC Enterprises  COMPANY
TIN003  XYZ Holdings     COMPANY
```

### PAYMENT

Existing fields:

```text
PAYMENT_ID
TAXPAYER_ID
AMOUNT
STATUS
PAYMENT_TIME
UPDATED_AT
```

Current payment states:

```text
PENDING
SUCCESSFUL
REVERSED
```

Business updates should set `UPDATED_AT = SYSTIMESTAMP` where appropriate.

---

## 6. CDC prerequisites already proven

Oracle already has:

- ARCHIVELOG enabled
- persistent recovery area
- minimum supplemental logging
- table-level ALL-column supplemental logging for source tables
- common Debezium LogMiner user
- working Oracle LogMiner capture

Do not rebuild this part unless a concrete failure requires it.

---

## 7. Debezium design

Two connectors exist intentionally.

### `oracle-cdc`

Native Debezium topics:

```text
oraclecdc.CDC_APP.PAYMENT
oraclecdc.CDC_APP.TAXPAYER
oraclecdc.CDC_APP.STATION
```

Purpose:

- preserve native envelope
- before/after inspection
- source/op metadata
- deep forensic debugging

### `oracle-cdc-flat`

Flat analytics topics:

```text
oracleflat.CDC_APP.PAYMENT
oracleflat.CDC_APP.TAXPAYER
oracleflat.CDC_APP.STATION
```

Important design concepts:

```text
decimal.handling.mode=string
ExtractNewRecordState SMT
schemas disabled
metadata fields copied before unwrap
delete records rewritten rather than silently lost
```

Flat events retain lineage fields such as:

```text
__op
__table
__source_scn
__source_commit_scn
__source_txId
__source_ssn
__source_commit_ts_ms
__source_user_name
__deleted
```

The flat connector exists to make ClickHouse ingestion simple while retaining useful lineage.

---

## 8. Kafka

Kafka runs in KRaft mode.

Important ClickHouse groups:

```text
clickhouse-oracle-payment-poc-v1
clickhouse-oracle-taxpayer-poc-v1
clickhouse-oracle-station-poc-v1
```

Consumer lag has already been demonstrated returning to zero.

Kafka is a durable event-streaming boundary. Do not bypass it with direct Oracle→ClickHouse application logic.

---

## 9. ClickHouse analytical model

Database:

```text
analytics
```

Raw CDC tables:

```text
raw_oracle_payment_cdc
raw_oracle_taxpayer_cdc
raw_oracle_station_cdc
```

The payment raw table carries business fields plus CDC lineage including:

```text
payment_id
taxpayer_id
amount
status
payment_time
updated_at
dbz_op
is_deleted
source_scn
source_commit_scn
source_tx_id
source_ssn
source_commit_time
source_user_name
event_version
kafka_topic
kafka_partition
kafka_offset
kafka_timestamp
ingested_at
```

Current/history objects already exist:

```text
fact_oracle_payment_current
dim_oracle_taxpayer_current
dim_oracle_station_current
dim_oracle_taxpayer_history
```

Serving view:

```text
vw_oracle_payment_analytics
```

It exposes business-friendly payment attributes plus station-at-payment and current-station semantics.

---

## 10. Historical semantic requirement

This has already been proven and must remain true.

Timeline:

```text
TIN001 at ST001 / Kampala Central
PAY102 happens
TIN001 moves ST001 → ST002 / Jinja
PAY103 happens
```

Correct analytical result:

```text
PAY102
station_at_payment = Kampala Central
current_station    = Jinja

PAY103
station_at_payment = Jinja
current_station    = Jinja
```

Do not replace the current SCD2/ASOF-style semantics with a naive join to the latest taxpayer row.

---

## 11. Ordering and time semantics

Keep these concepts separate:

```text
PAYMENT_TIME       business event time
UPDATED_AT         application row update time
source_commit_time Oracle commit/CDC time
kafka_timestamp    Kafka timestamp
ingested_at        ClickHouse ingestion time
```

`ingested_at` is observability metadata, not authoritative source ordering.

Current-state logic must continue using source-derived version information such as commit SCN/SCN, source sequence metadata and Kafka lineage as a final deterministic tiebreaker where required.

---

## 12. Simulator

Existing files:

```text
simulator/oracle_simulator.py
simulator/run_load.py
```

The simulator writes only to Oracle.

Typical continuous workload:

```text
80% new payments
15% payment status updates
5% taxpayer station moves
```

Example:

```bash
python simulator/run_load.py --transactions-per-minute 10
```

Preserve this rule when adding web simulator controls.

---

## 13. UI direction

Approved visual style:

- dark navy sidebar
- warm yellow/gold primary buttons and selected navigation
- white/light-gray workspace
- compact professional tables
- restrained card shadows and borders
- green success
- amber pending/warning
- red reversed/danger
- no logo
- no CDC jargon on normal business pages

Suggested CSS tokens:

```css
--navy: #0B1F3A;
--navy-2: #112A4D;
--yellow: #F5B400;
--yellow-hover: #E6A800;
--background: #F5F7FA;
--surface: #FFFFFF;
--text-primary: #182230;
--text-muted: #6B7280;
--border: #E5E7EB;
--success: #15803D;
--warning: #B45309;
--danger: #B91C1C;
```

Status badges should be used only for entities that actually have a source status, such as PAYMENT. Do not invent taxpayer/station status just for presentation.

---

## 14. Frontend approach

Use:

```text
FastAPI
Jinja2/server-served index.html
HTML
CSS
vanilla JavaScript
fetch()
```

Do not introduce React/Vue/Angular/Vite/npm for the POC unless a concrete blocker appears.

The app should have a SPA-like experience:

```text
persistent sidebar
persistent header
dynamic main content
right-side drawer
modal layer
toast layer
```

---

## 15. Screen behavior

### Dashboard

Reads ClickHouse.

Business-facing KPIs:

```text
Total Taxpayers
Total Stations
Payments Today
Amount Collected Today
```

Content can include:

```text
Payments by Station
Payment Status Breakdown
Recent Payments
Recent Taxpayer Activity
```

Do not show `Active Stations` unless a real lifecycle field is later approved and added to the source system.

### Taxpayers

Reads/writes Oracle.

Current-phase features:

- search
- type/station filters
- create drawer
- edit drawer
- station reassignment

No normal hard delete.

Deactivate/reactivate is deferred.

### Stations

Reads/writes Oracle.

Current-phase features:

- list/search
- create/edit
- region/district fields

No normal hard delete.

Deactivate/reactivate is deferred.

### Payments

Reads/writes Oracle.

Features:

- KPI strip
- payment search
- status/date filters
- create payment drawer
- payment detail drawer
- status transitions

Approved state machine:

```text
PENDING → SUCCESSFUL
PENDING → REVERSED
SUCCESSFUL → REVERSED
REVERSED → terminal
```

No hard delete.

### Reports

Lightweight operational summaries only. Do not rebuild Power BI.

### Pipeline Health

Engineering screen with:

```text
Oracle status
Debezium connector/task status
Kafka consumer lag
ClickHouse status
last event timestamps
approximate latency
```

### Event Monitor

Audit/engineering view showing:

```text
entity
operation
business ID
source SCN
commit SCN
transaction ID
source user
Kafka topic/partition/offset
ClickHouse ingestion time
latency
```

For updates, derive friendly before/after values where possible.

### Simulator

Controls for:

```text
start
stop
transactions per minute
traffic mix
recent generated activity
```

The simulator still writes only to Oracle.

---

## 16. FastAPI route contract

### Oracle-backed operational API

Current phase:

```text
GET    /api/taxpayers
GET    /api/taxpayers/{tin}
POST   /api/taxpayers
PUT    /api/taxpayers/{tin}

GET    /api/stations
GET    /api/stations/{id}
POST   /api/stations
PUT    /api/stations/{id}

GET    /api/payments
GET    /api/payments/{id}
POST   /api/payments
POST   /api/payments/{id}/status
```

Deferred, do not implement now:

```text
/api/taxpayers/{tin}/deactivate
/api/taxpayers/{tin}/activate
/api/stations/{id}/deactivate
/api/stations/{id}/activate
```

### ClickHouse-backed analytical API

```text
GET /api/dashboard/summary
GET /api/dashboard/payments-by-station
GET /api/dashboard/status-summary
GET /api/dashboard/recent-activity
GET /api/reports/payments
GET /api/events
GET /api/events/{entity}/{id}
```

### Infrastructure API

```text
GET /api/pipeline/health
```

### Simulator API

```text
POST /api/simulator/start
POST /api/simulator/stop
GET  /api/simulator/status
```

---

## 17. Validation and errors

FastAPI is authoritative. Frontend checks are convenience only.

Payment creation validates:

```text
amount > 0
taxpayer exists
referenced taxpayer station exists
status allowed
payment ID unique
```

Payment update validates the approved state machine.

Do not add ACTIVE/INACTIVE checks for taxpayer/station in this phase.

Use a stable API error shape:

```json
{
  "error": "invalid_status_transition",
  "message": "A reversed payment cannot be marked successful."
}
```

Suggested HTTP behavior:

```text
201 Created
404 Not Found
409 Conflict
422 Validation Error
503 Service Unavailable
```

Never leak raw `ORA-xxxx`, credentials, connection strings, SQL or stack traces to the browser.

---

## 18. Failure isolation

If Debezium is down:

```text
Taxpayers / Stations / Payments continue against Oracle.
Pipeline Health shows degraded.
```

If ClickHouse is down:

```text
source operations continue
Dashboard/Reports/Event Monitor show analytics unavailable
```

This separation is an important architecture demonstration.

---

## 19. Project structure target

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
└── static/
    ├── css/
    └── js/

simulator/
tests/
docs/
.env.example
requirements.txt
```

Responsibilities:

```text
routes        HTTP concerns
services      business rules
schemas       request/response validation
oracle.py     Oracle access
clickhouse.py ClickHouse access
static/js     browser behavior
static/css    design system
```

Avoid a monolithic `main.py` and avoid SQL scattered through route handlers.

---

## 20. Security boundaries

Even without authentication:

- no arbitrary SQL API
- no arbitrary shell API
- no arbitrary Kafka produce endpoint
- no secrets in Git
- no credentials returned to browser
- use bind parameters for Oracle
- parameterize ClickHouse queries where supported
- `.env` must remain ignored

---

## 21. Polling

Do not add WebSockets initially.

Suggested refresh intervals:

```text
Dashboard          ~10 seconds
Pipeline Health    ~5 seconds
Event Monitor      ~2 seconds while LIVE
Simulator status   ~2 seconds
```

---

## 22. Testing requirements

Business-rule tests should include:

```text
PENDING → SUCCESSFUL allowed
PENDING → REVERSED allowed
SUCCESSFUL → REVERSED allowed
REVERSED → SUCCESSFUL rejected
negative amount rejected
zero amount rejected
missing taxpayer rejected
missing taxpayer station reference rejected
```

Do not add tests that assume taxpayer/station ACTIVE/INACTIVE fields.

Critical end-to-end smoke test:

```text
POST payment through FastAPI
        ↓
verify Oracle row
        ↓
wait for CDC
        ↓
verify ClickHouse raw/current
        ↓
verify serving view
```

---

## 23. Deployment

Development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Target internal URL:

```text
http://10.1.78.38:8000
```

Stable deployment should use systemd with an environment file and automatic restart.

Do not change network controls until actual accessibility is tested from the intended demo host.

---

## 24. Explicit non-goals

Do not add unless later requested:

```text
authentication
JWT
roles
React/Vue/Angular
Node/npm build chain
WebSockets
Kafka admin console
SQL editor
general shell runner
replacement for Power BI
large reporting engine
TAXPAYER.STATUS
STATION.STATUS
taxpayer/station deactivate-reactivate workflow
```

---

## 25. Implementation order

```text
Phase 0  inspect repository and confirm schema
Phase 1  application shell
Phase 2  Payments vertical slice
Phase 3  Taxpayers create/edit/reassign
Phase 4  Stations create/edit
Phase 5  Dashboard
Phase 6  Event Monitor
Phase 7  Pipeline Health
Phase 8  Simulator Control
Phase 9  Reports
Phase 10 systemd/deployment
```

---

## 26. First milestone acceptance

The first milestone is:

```text
Application shell + Payments vertical slice
```

It must provide:

- FastAPI startup
- navy/yellow shell
- SPA-style navigation
- Oracle-backed payment table
- Create Payment drawer
- Payment Detail drawer
- payment state transitions
- friendly errors and toasts

Creating a payment must follow:

```text
UI → FastAPI → Oracle COMMIT → Debezium → Kafka → ClickHouse
```

No source-schema change to TAXPAYER or STATION is required for this milestone.

---

## 27. Codex instructions

Before coding:

1. Inspect the repository.
2. Preserve the existing Docker/CDC infrastructure.
3. Treat current Oracle TAXPAYER/STATION schema as frozen.
4. Do not add STATUS columns to those tables.
5. Build against the fields that actually exist.
6. Do not publish business events to Kafka from the application.
7. Do not write business rows directly to ClickHouse.
8. Implement one vertical slice at a time.
9. Add tests around payment business rules.
10. Preserve historical station-at-payment semantics.

If repository reality differs from this document, preserve working infrastructure and ask before making source-schema changes.

---

## 28. Product principle

To a business user:

> This is a normal internal transactional application.

To an engineer:

> Every committed Oracle change is captured from redo through Debezium and Kafka into ClickHouse, without the source application knowing anything about the analytics pipeline.

That separation is the central idea of the POC.
