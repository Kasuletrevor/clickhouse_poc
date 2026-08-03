# Oracle → Debezium CDC POC for `Efris_codes`

## Purpose

This document defines the Oracle-side requirements for a small Change Data Capture proof of concept using **Debezium Oracle LogMiner**.

The first and only table in scope is:

```text
Efris_codes
```

The table owner/schema will be confirmed with the Oracle DBA before the connector is configured. In connector configuration and SQL checks, use the fully qualified name:

```text
<SCHEMA>.Efris_codes
```

The scope of this document is deliberately limited to **Oracle and Debezium**. Kafka, ClickHouse, Power BI, and the application layer are outside this DBA setup request.

---

## What the POC will prove

The POC should demonstrate that when a row in `Efris_codes` is inserted, updated, or deleted in the Oracle test database, Debezium can detect the committed change from Oracle redo/archive logs and publish the corresponding CDC event.

The source of truth remains Oracle. Debezium does not write to `Efris_codes`; it reads committed database changes through Oracle LogMiner.

---

## What we need from the Oracle DBA

### 1. Oracle connection information

Please provide or confirm:

```text
Oracle hostname / IP
Listener port
Service name
PDB name, if applicable
Schema/owner of Efris_codes
Oracle database version
Whether the database is CDB/PDB
Whether the environment uses RAC
Whether ASM is used for redo/archive logs
```

No SYS or SYSTEM credentials are required by the Debezium application.

---

## 2. Confirm the Oracle database topology

Please run:

```sql
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';
```

Then:

```sql
SELECT
    name,
    db_unique_name,
    cdb,
    log_mode,
    supplemental_log_data_min
FROM v$database;
```

If the database is multitenant, also confirm the PDB containing `Efris_codes`:

```sql
SELECT name, open_mode
FROM v$pdbs;
```

The Debezium user and connector configuration will be adjusted to match the actual CDB/PDB topology.

---

## 3. Confirm `Efris_codes`

The DBA should confirm the owner and table metadata:

```sql
SELECT
    owner,
    table_name,
    logging,
    num_rows,
    last_analyzed
FROM dba_tables
WHERE UPPER(table_name) = 'EFRIS_CODES';
```

Confirm the columns:

```sql
SELECT
    owner,
    table_name,
    column_id,
    column_name,
    data_type,
    data_length,
    nullable
FROM dba_tab_columns
WHERE UPPER(table_name) = 'EFRIS_CODES'
ORDER BY owner, column_id;
```

Confirm the primary key or other unique identifier:

```sql
SELECT
    c.owner,
    c.constraint_name,
    c.constraint_type,
    cc.column_name,
    cc.position
FROM dba_constraints c
JOIN dba_cons_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
WHERE UPPER(c.table_name) = 'EFRIS_CODES'
  AND c.constraint_type IN ('P', 'U')
ORDER BY c.owner, c.constraint_name, cc.position;
```

A stable primary key is strongly preferred for CDC because it gives Debezium an unambiguous key for each row-level change.

---

## 4. ARCHIVELOG requirement

Debezium LogMiner needs Oracle redo information and normally relies on online redo plus archived redo logs.

Confirm:

```sql
SELECT log_mode
FROM v$database;
```

Expected:

```text
ARCHIVELOG
```

If the test database is not in `ARCHIVELOG` mode, the DBA should review enabling it before the POC proceeds.

The existing archive-log retention/deletion policy should also be reviewed. The retained logs must cover the period from the last SCN processed by Debezium until the connector resumes after an outage.

---

## 5. Enable minimal supplemental logging

Confirm the current setting:

```sql
SELECT supplemental_log_data_min
FROM v$database;
```

If minimal supplemental logging is not enabled, the DBA can enable it at database level:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
```

Recheck:

```sql
SELECT supplemental_log_data_min
FROM v$database;
```

Expected:

```text
YES
```

---

## 6. Enable supplemental logging only for `Efris_codes`

For this POC, do **not** enable ALL COLUMN supplemental logging across the entire test database.

Apply it only to the agreed table:

```sql
ALTER TABLE <SCHEMA>.Efris_codes
ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

Confirm the table-level supplemental log group:

```sql
SELECT
    owner,
    table_name,
    log_group_name,
    log_group_type,
    always
FROM dba_log_groups
WHERE UPPER(table_name) = 'EFRIS_CODES'
ORDER BY owner, log_group_name;
```

This keeps the POC narrow and limits additional redo generation to the table being tested.

---

## 7. Create a dedicated Debezium LogMiner user

Use a dedicated account for CDC, for example:

```text
CDC_DEBEZIUM
```

The exact user creation location depends on whether the Oracle environment is non-CDB or multitenant. The DBA should create the account in the correct container and apply the minimum privileges required by Debezium Oracle LogMiner.

Typical LogMiner-related privileges include:

```sql
GRANT CREATE SESSION TO CDC_DEBEZIUM;
GRANT LOGMINING TO CDC_DEBEZIUM;
GRANT SELECT ANY TRANSACTION TO CDC_DEBEZIUM;
GRANT SELECT_CATALOG_ROLE TO CDC_DEBEZIUM;
GRANT EXECUTE_CATALOG_ROLE TO CDC_DEBEZIUM;
```

Debezium also requires read access to Oracle dictionary and dynamic performance views used to discover redo logs, transactions, SCNs, database metadata, and LogMiner state. The exact grants should be aligned with the Oracle version and local security policy rather than granting DBA privileges.

No DBA role should be granted to `CDC_DEBEZIUM`.

---

## 8. Grant snapshot/read access only to the POC table

For the initial Debezium snapshot, prefer table-specific permissions instead of broad `SELECT ANY TABLE` / `FLASHBACK ANY TABLE` where the local security policy permits it.

Example:

```sql
GRANT SELECT ON <SCHEMA>.Efris_codes TO CDC_DEBEZIUM;
GRANT FLASHBACK ON <SCHEMA>.Efris_codes TO CDC_DEBEZIUM;
```

If the Oracle version/topology requires broader grants for the connector, the DBA should approve those explicitly.

---

## 9. Network connectivity

The Debezium/Kafka Connect host must be able to reach the Oracle test listener.

Required path:

```text
Debezium host
    → Oracle test hostname/IP
    → Oracle listener port
    → configured service/PDB
```

Only normal Oracle client connectivity is required. Debezium is not installed inside the Oracle database server.

A simple connectivity check from the Debezium host should be performed before connector registration.

---

## 10. Debezium connector scope

The connector must initially include only `Efris_codes`.

Conceptually:

```json
{
  "connector.class": "io.debezium.connector.oracle.OracleConnector",
  "database.connection.adapter": "logminer",
  "table.include.list": "<SCHEMA>.EFRIS_CODES"
}
```

The full connector JSON will be prepared after the DBA confirms:

```text
Oracle version
hostname
listener port
service/PDB
schema owner
CDC username
primary-key structure of Efris_codes
```

Credentials will not be committed to GitHub.

---

## 11. Validation procedure

After Oracle and Debezium are configured, use a controlled test row in `Efris_codes`.

The sequence should be:

```text
1. Start Debezium connector.
2. Confirm initial snapshot completes.
3. INSERT one agreed test row in Efris_codes.
4. COMMIT.
5. Confirm Debezium emits a create event (`op = c`).
6. UPDATE the same test row.
7. COMMIT.
8. Confirm Debezium emits an update event (`op = u`).
9. DELETE the agreed test row only if deletion is approved for the POC.
10. COMMIT.
11. Confirm Debezium emits a delete event (`op = d`).
```

The business table must not be modified merely to generate traffic unless the DBA/table owner has approved the exact test record and test window.

---

## 12. Oracle-side acceptance checks

Before registering the Debezium connector, confirm all of the following:

- [ ] Oracle version/topology has been recorded.
- [ ] Schema/owner of `Efris_codes` is known.
- [ ] `Efris_codes` column structure is known.
- [ ] Primary key or unique business key is confirmed.
- [ ] Database is in `ARCHIVELOG` mode.
- [ ] Minimal supplemental logging is enabled.
- [ ] `ALL COLUMNS` supplemental logging is enabled only on `<SCHEMA>.Efris_codes` for this POC.
- [ ] Dedicated `CDC_DEBEZIUM` account exists.
- [ ] The account has the approved LogMiner/catalog/V$ privileges.
- [ ] The account can SELECT/FLASHBACK the POC table for snapshotting.
- [ ] The Debezium host can reach the Oracle listener.
- [ ] Archive-log retention is sufficient for temporary connector downtime.

---

## What is not required from the DBA

For this Oracle/Debezium POC, the DBA is **not** being asked to:

```text
Install Debezium on the Oracle server
Install Kafka on the Oracle server
Provide SYS/SYSTEM credentials to the connector
Grant DBA to the Debezium user
Enable ALL COLUMN supplemental logging for every database table
Modify production
Create database links
```

The POC is intentionally limited to the Oracle test environment and the single table `Efris_codes`.

---

## DBA handoff summary

The immediate DBA request is therefore:

1. Confirm Oracle version and topology.
2. Confirm the owner/schema and key structure of `Efris_codes`.
3. Confirm/enable `ARCHIVELOG` and minimal supplemental logging.
4. Add table-level ALL COLUMN supplemental logging only to `Efris_codes`.
5. Create a dedicated least-privilege Debezium LogMiner account.
6. Grant snapshot access to `Efris_codes` and the required LogMiner/catalog/V$ access.
7. Confirm network connectivity and archive-log retention.
8. Return the connection metadata required for connector configuration.

Once these are confirmed, the Debezium connector can be registered with `table.include.list` restricted to `<SCHEMA>.EFRIS_CODES` and the end-to-end CDC test can begin.
