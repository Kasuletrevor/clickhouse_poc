# Dashboard Design — Internal Transaction Application

**Date:** 2026-08-02  
**Branch:** `feature/internal-transaction-app`  
**Scope:** ClickHouse-backed business dashboard for the Oracle → Debezium → Kafka → ClickHouse CDC POC

## 1. Purpose

Add a polished business-facing Dashboard that makes the analytical side of the CDC pipeline visible without exposing CDC jargon to normal users.

The Dashboard must read from ClickHouse only. Operational source-system screens remain Oracle-backed and continue to function independently if ClickHouse is unavailable.

The Dashboard should feel more executive than the operational Payments, Taxpayers and Stations pages: KPIs and charts must visually stand out, while lower-page activity remains compact and operationally useful.

## 2. Approved scope

The Dashboard contains:

1. Four prominent KPIs:
   - Total Taxpayers
   - Total Stations
   - Payments Today
   - Amount Collected Today
2. Payments by Station chart
3. Payment Status Breakdown chart
4. Recent Payments
5. Recent Taxpayer Activity derived from CDC history
6. Last-refresh indicator
7. Automatic refresh approximately every 10 seconds

The Dashboard does not write to Oracle, Kafka or ClickHouse.

## 3. Data-source split

Use a hybrid ClickHouse approach.

### Business/current-state analytics

Prefer the established serving/current objects:

- `analytics.vw_oracle_payment_analytics`
- `analytics.fact_oracle_payment_current`
- `analytics.dim_oracle_taxpayer_current`
- `analytics.dim_oracle_station_current`

These objects provide current business state and historical station-at-payment semantics.

### Recent taxpayer activity

Use:

- `analytics.raw_oracle_taxpayer_cdc`

The activity feed must represent actual change events rather than merely sorting the latest taxpayer dimension rows.

Source-derived ordering must be used for event chronology. `ingested_at` is observability metadata and must not become authoritative ordering where source commit metadata is available.

## 4. KPI definitions

### Total Taxpayers

Count current, non-deleted taxpayer records from `dim_oracle_taxpayer_current`.

### Total Stations

Count current, non-deleted station records from `dim_oracle_station_current`.

Do not label this as "Active Stations" because the source schema does not contain a station lifecycle/status field.

### Payments Today

Count current payment records whose business `payment_time` falls on the current calendar date used by the analytical environment.

### Amount Collected Today

Sum payment `amount` for payments occurring today that are currently `SUCCESSFUL`.

This KPI represents collected revenue, so pending and reversed payments must not contribute to the collected amount.

## 5. Visual hierarchy

The Dashboard uses the existing dark-navy sidebar and light workspace, but its main content has stronger hierarchy than the operational pages.

### KPI row

Four large cards across the top on desktop:

- larger numeric type than operational-page KPIs
- generous whitespace
- restrained gold/navy accent treatment
- concise supporting text
- Amount Collected Today receives the strongest monetary emphasis
- UGX values use compact readable formatting where appropriate, such as `UGX 41.25M`

The KPI cards must not look like small utility counters.

### Chart row

Two prominent chart panels below the KPI row.

#### Payments by Station

Use a bar chart because relative magnitude and ranking matter.

- business station names on the category axis
- payment amount as the primary measure
- show exact/compact values in tooltips or labels
- order stations by amount descending where practical
- avoid rainbow coloring; use a restrained palette consistent with the navy/gold application design

#### Payment Status Breakdown

Use a donut chart because the approved payment states form a small part-to-whole composition:

- SUCCESSFUL
- PENDING
- REVERSED

Use semantic status colors consistent with the rest of the app:

- successful: green
- pending: amber/gold
- reversed: red

Show counts and/or percentages clearly enough that the chart does not rely on color alone.

## 6. Lower dashboard panels

### Recent Payments

Display a compact recent-payment table/list with:

- payment ID
- taxpayer ID/name
- amount
- status
- payment time
- station-at-payment where available

This section is analytical and reads ClickHouse, not Oracle.

### Recent Taxpayer Activity

Translate raw taxpayer CDC rows into business-facing activity descriptions.

Supported friendly activities include:

- Taxpayer created
- Taxpayer details updated
- Station changed

A station-change item should present a friendly before/after value such as:

`Kampala Central → Jinja`

Where station names cannot be resolved, fall back to station IDs rather than dropping the event.

Do not show source SCN, commit SCN, transaction ID, Kafka topic/partition/offset, or ClickHouse ingestion time on the normal Dashboard. Those details belong to the later Event Monitor screen.

## 7. Dashboard API

Use ClickHouse-backed routes:

- `GET /api/dashboard/summary`
- `GET /api/dashboard/payments-by-station`
- `GET /api/dashboard/status-summary`
- `GET /api/dashboard/recent-activity`

### `/api/dashboard/summary`

Returns at minimum:

```json
{
  "total_taxpayers": 3,
  "total_stations": 3,
  "payments_today": 47,
  "amount_collected_today": 41250000,
  "refreshed_at": "2026-08-02T16:00:00Z"
}
```

### `/api/dashboard/payments-by-station`

Returns station-level payment totals suitable for the chart, including station ID/name, payment count and successful amount.

### `/api/dashboard/status-summary`

Returns the three approved payment states with counts and amounts where useful.

### `/api/dashboard/recent-activity`

Returns two arrays so the browser can render the lower panels without extra round trips:

- `recent_payments`
- `recent_taxpayer_activity`

Taxpayer activity items contain a friendly action label/message plus enough structured fields for presentation.

## 8. ClickHouse access boundary

Add a dedicated ClickHouse access layer rather than putting HTTP/SQL calls directly into route handlers.

Suggested responsibility split:

- `app/clickhouse.py` — connection/client handling and safe ClickHouse exceptions
- `app/repositories/dashboard.py` — analytical SQL only
- `app/services/dashboard.py` — response shaping and friendly activity translation
- `app/routes/dashboard.py` — HTTP concerns
- `app/static/js/dashboard.js` — rendering, polling, chart behavior

The Dashboard must not reuse the Oracle repository layer for analytical reads.

## 9. Failure isolation

If ClickHouse is unavailable:

- Dashboard displays a clear analytics-unavailable state
- Oracle-backed Payments, Taxpayers and Stations continue to work
- no raw ClickHouse exception, SQL, credentials, hostnames or stack traces are returned to the browser

Use a stable error response consistent with the existing application style.

## 10. Refresh behavior

The Dashboard refreshes approximately every 10 seconds while it is the active page.

Requirements:

- initial load happens immediately
- show a last-refresh timestamp
- avoid overlapping refresh requests
- stop/release the polling timer when navigating away
- a transient refresh failure should preserve the last good rendered data where practical and surface a restrained error state/toast

This behavior is intentionally slow enough to avoid unnecessary load while still making CDC propagation visible during demonstrations.

## 11. Frontend/chart implementation

Stay within the approved frontend stack:

- server-served HTML
- existing CSS
- vanilla JavaScript
- `fetch()`

Do not introduce React, Vue, Angular, Vite or npm.

For charts, prefer a lightweight browser chart library only if it materially reduces complexity and can be served locally without introducing a frontend build toolchain. If the project already has no chart dependency, an implementation plan must explicitly choose either:

1. a small vendored/browser-loaded chart library with no build step, or
2. simple native SVG/canvas chart rendering in `dashboard.js`.

The implementation must preserve the application’s navy/gold visual identity and semantic payment-state colors.

## 12. Testing

Add automated tests for:

- dashboard summary response shape
- successful amount excludes PENDING and REVERSED payments
- station aggregation response shape/order
- payment status summary
- taxpayer CDC activity translation for create/update/station reassignment
- ClickHouse failure mapped to a safe analytics-unavailable response
- app shell routes Dashboard navigation to the real Dashboard page rather than the placeholder

Host verification must include the real ClickHouse-backed endpoints after pulling to `datalake-test02`.

## 13. Non-goals

This slice does not implement:

- Reports
- Pipeline Health
- Event Monitor
- Simulator controls
- Power BI replacement
- authentication/authorization
- taxpayer/station status fields
- direct writes to ClickHouse
- direct Kafka publishing

## 14. Success criteria

The Dashboard is ready when:

1. all automated tests pass on the RHEL Python 3.9 environment;
2. all four KPIs return live ClickHouse values;
3. Payments by Station and Payment Status Breakdown render clearly and prominently;
4. Recent Payments comes from ClickHouse;
5. Recent Taxpayer Activity is based on raw taxpayer CDC history and shows friendly business descriptions;
6. the Dashboard refreshes automatically without page reload;
7. ClickHouse failure does not break the Oracle-backed operational screens;
8. no CDC jargon appears in normal Dashboard presentation text.
