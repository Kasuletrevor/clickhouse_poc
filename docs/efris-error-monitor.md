# EFRIS Error CDC Monitor

## Purpose

This document records the EFRIS error-log extension added to the existing Oracle → Debezium → Kafka → ClickHouse proof of concept.

The current milestone proves that an EFRIS-style invoice error can be created in the source application, committed to Oracle, captured from redo by Debezium, published to Kafka, materialized in ClickHouse, and displayed in the internal web application.

The architecture rule remains unchanged:

```text
WRITE PATH
Browser / simulator → FastAPI → Oracle

CDC PATH
Oracle redo → Debezium LogMiner → Kafka → ClickHouse

ANALYTICS PATH
ClickHouse → FastAPI analytical API → browser
```

The web application never writes directly to Kafka or ClickHouse.

---

## Source objects added in Oracle

### `CDC_APP.EFRIS_DEVICE`

Stores EFRIS devices assigned to taxpayers.

Current proof-of-concept devices include:

```text
TIN001_01  TIN001  1  POS
TIN001_02  TIN001  2  POS
TIN001_03  TIN001  3  POS
TIN002_01  TIN002  1  ERP
TIN003_01  TIN003  1  ERP
TIN003_02  TIN003  2  ERP
TIN278_01  TIN278  1  ERP
```

The table has:

- primary key on `DEVICE_NO`;
- unique constraint on `(TAXPAYER_ID, DEVICE_SEQ)`;
- foreign key from `TAXPAYER_ID` to `CDC_APP.TAXPAYER`.

### `CDC_APP.T_INVOICE_ERROR_LOG`

EFRIS-style error source table.

Important columns include:

```text
ERROR_EVENT_ID
ID
TIN
DEVICE_NO
SELLER_REFERENCE_NO
RETURN_CODE
RETURN_MSG
GROSS_AMOUNT
TAX_AMOUNT
CURRENCY
ITEM_DESCRIPTION
CREATE_USER_ID
CREATE_DATE
UPDATE_USER_ID
UPDATE_DATE
```

`ERROR_EVENT_ID` is the local surrogate primary key because the production-style `ID` field is not guaranteed to be unique.

Foreign keys connect:

```text
TIN       → TAXPAYER.TAXPAYER_ID
DEVICE_NO → EFRIS_DEVICE.DEVICE_NO
```

Table-level supplemental logging was enabled:

```sql
ALTER TABLE CDC_APP.T_INVOICE_ERROR_LOG ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

Oracle confirmed:

```text
ALL COLUMN LOGGING  ALWAYS
```

### `CDC_APP.T_INVOICE`

A successful-invoice table was also created for the later error-resolution lifecycle work. It is not required for the current error-stream dashboard milestone.

### `CDC_APP.SEQ_EFRIS_SELLER_REF`

Used to generate proof-of-concept seller reference numbers when the application does not supply one.

---

## Debezium configuration

The existing flat Oracle connector remains:

```text
oracle-cdc-flat
```

It uses Oracle LogMiner and the `ExtractNewRecordState` SMT.

The table include list was extended from:

```text
CDC_APP.STATION,CDC_APP.TAXPAYER,CDC_APP.PAYMENT
```

to:

```text
CDC_APP.STATION,CDC_APP.TAXPAYER,CDC_APP.PAYMENT,CDC_APP.T_INVOICE_ERROR_LOG
```

Existing connector settings were preserved.

Important settings include:

```text
topic.prefix=oracleflat
snapshot.mode=initial
decimal.handling.mode=string
```

The connector and task were verified as `RUNNING` after the configuration change.

---

## Kafka proof

The EFRIS error topic is:

```text
oracleflat.CDC_APP.T_INVOICE_ERROR_LOG
```

A committed Oracle error event was captured automatically by Debezium and observed in Kafka.

Example payload fields:

```json
{
  "ERROR_EVENT_ID": "1",
  "TIN": "TIN001",
  "DEVICE_NO": "TIN001_01",
  "SELLER_REFERENCE_NO": "TIN001-INV-00000001",
  "RETURN_CODE": "1600",
  "GROSS_AMOUNT": "224200.00000000",
  "TAX_AMOUNT": "30691.53000000",
  "CURRENCY": "UGX",
  "__op": "c",
  "__table": "T_INVOICE_ERROR_LOG",
  "__source_scn": "6553758",
  "__source_commit_scn": "6553865",
  "__source_user_name": "CDC_APP"
}
```

This proves the event came through Oracle redo/LogMiner rather than a manual Kafka producer.

---

## ClickHouse ingestion

### Kafka Engine table

```text
analytics.efris_error_kafka_queue
```

Consumes:

```text
oracleflat.CDC_APP.T_INVOICE_ERROR_LOG
```

with consumer group:

```text
clickhouse-efris-error-poc-v1
```

### Persistent raw table

```text
analytics.raw_efris_error_log
```

The table preserves:

- EFRIS business fields;
- Oracle source SCN/commit metadata;
- Kafka topic/partition/offset lineage;
- ClickHouse ingestion time.

### Materialized view

```text
efris_error_kafka_to_raw_mv
```

The materialized view continuously transfers rows from the Kafka Engine table into `raw_efris_error_log`.

The first batch was verified in ClickHouse with seven rows including codes:

```text
1600
3077
2249
2253
2785
1332
```

The `2785` event was intentionally present twice as separate source error events, demonstrating that the raw table stores event history rather than forcing business-level deduplication.

---

## Internal web application

The EFRIS monitor is implemented inside the existing FastAPI + HTML/CSS + vanilla JavaScript application on branch:

```text
feature/efris-error-monitor
```

The page is available from the sidebar as:

```text
EFRIS Errors
```

### Analytical reads

The analytical page reads ClickHouse only.

Endpoint:

```text
GET /api/efris-errors/dashboard?minutes=60
```

Supported time windows in the UI:

```text
15 minutes
1 hour
24 hours
7 days
```

The dashboard returns:

- error event count;
- distinct affected seller references;
- distinct taxpayers;
- distinct EFRIS devices;
- UGX gross amount associated with errors;
- UGX tax amount associated with errors;
- error trend over time;
- top return codes;
- top affected taxpayers;
- recent error events.

The page refreshes automatically every five seconds.

### Source event creation

The same EFRIS page can now create a new error event using the `+ New Error Event` drawer.

The write path is deliberately source-only:

```text
Browser
  ↓
POST /api/efris-errors
  ↓
FastAPI
  ↓
CDC_APP.T_INVOICE_ERROR_LOG
  ↓ COMMIT
Oracle redo
  ↓
Debezium
  ↓
Kafka
  ↓
ClickHouse
  ↓
EFRIS dashboard auto-refresh
```

The application does not publish to Kafka itself.

The creation form supports:

- taxpayer selection;
- EFRIS device selection filtered by taxpayer;
- common EFRIS return codes;
- editable return message;
- optional seller reference;
- gross amount;
- tax amount;
- currency;
- item description.

If the seller reference is omitted, the backend generates one using `SEQ_EFRIS_SELLER_REF`.

The backend also generates a source event `ID` for web-created POC events.

Device ownership is validated before insert. A device cannot be used for a different taxpayer.

Supporting endpoint:

```text
GET /api/efris-errors/devices?tin=TIN001
```

Create endpoint:

```text
POST /api/efris-errors
```

Example request:

```json
{
  "tin": "TIN001",
  "device_no": "TIN001_02",
  "seller_reference_no": null,
  "return_code": "3077",
  "return_msg": "Buyer TIN is required and cannot be empty",
  "gross_amount": 850000,
  "tax_amount": 129661.02,
  "currency": "UGX",
  "item_description": "POC ELECTRONICS"
}
```

The immediate API response confirms that the transaction was committed to Oracle. Appearance in the analytical table is asynchronous because the event still has to travel through Debezium, Kafka and ClickHouse.

---

## Current code structure

```text
app/
├── main.py
├── repositories/
│   ├── efris_errors.py      # ClickHouse analytical reads
│   └── efris_events.py      # Oracle source writes/device lookup
├── routes/
│   └── efris_errors.py
├── schemas/
│   └── efris_errors.py
├── services/
│   ├── efris_errors.py      # analytical service
│   └── efris_events.py      # source-event service
├── static/js/
│   └── efris_errors.js
└── templates/
    └── index.html
```

This deliberately keeps source writes and analytical reads separated even though they are presented on one business page.

---

## Quick test flow

Start the FastAPI application using the existing environment configuration:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open the internal application and select **EFRIS Errors**.

Create an event from **+ New Error Event**.

The application should immediately confirm that the event was committed to Oracle.

Then verify the downstream path if required:

```text
Oracle T_INVOICE_ERROR_LOG
        ↓
Debezium connector RUNNING
        ↓
Kafka topic oracleflat.CDC_APP.T_INVOICE_ERROR_LOG
        ↓
ClickHouse raw_efris_error_log
        ↓
EFRIS Error Monitor
```

The dashboard will pick up the event automatically once ClickHouse ingests it.

---

## Current milestone status

```text
Oracle EFRIS-style source schema      COMPLETE
Supplemental logging                 COMPLETE
Debezium capture                     COMPLETE
Kafka topic                          COMPLETE
Kafka event proof                    COMPLETE
ClickHouse Kafka Engine              COMPLETE
ClickHouse persistent raw table      COMPLETE
ClickHouse materialized ingestion    COMPLETE
EFRIS analytical backend             IMPLEMENTED
EFRIS analytical UI                  IMPLEMENTED
Create-error-event backend           IMPLEMENTED
Create-error-event UI                IMPLEMENTED
```

The next useful step is runtime verification of the new FastAPI route and browser drawer on the RHEL POC server, followed by one browser-created event being observed end-to-end in ClickHouse.
