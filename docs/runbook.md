# Operations Runbook

This runbook captures the routine operating commands for the current CDC POC on `datalake-test02`.

Run commands from:

```bash
cd /home/jkasule/cdc-clickhouse-poc
```

Do not paste credentials into documentation or Git history.

---

## 1. Check Docker services

```bash
sudo docker compose ps
```

Expected service set includes:

```text
poc-oracle
poc-debezium
poc-kafka
poc-kafbat
poc-clickhouse
```

Useful broad check:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

---

## 2. Start/stop the stack

Start:

```bash
sudo docker compose up -d
```

Stop containers without deleting persistent data:

```bash
sudo docker compose stop
```

Start stopped containers:

```bash
sudo docker compose start
```

Restart a single service when required:

```bash
sudo docker compose restart <service>
```

Avoid `down -v` unless you intentionally want to remove persistent volumes/data.

---

## 3. Oracle

### Connect as SYSDBA

```bash
sudo docker exec -it poc-oracle sqlplus / as sysdba
```

### Connect as application schema

Use the current application password from the environment, not from Git.

Example pattern:

```bash
sudo docker exec -it poc-oracle \
  sqlplus CDC_APP/"$CDC_APP_PASSWORD"@//localhost:1521/FREEPDB1
```

If the shell variable is not exported in the invoking environment, authenticate interactively instead of placing a password in command history.

### Basic database checks

Inside SQL*Plus:

```sql
SHOW PDBS;
```

Check application rows:

```sql
SELECT PAYMENT_ID, TAXPAYER_ID, AMOUNT, STATUS, PAYMENT_TIME
FROM CDC_APP.PAYMENT
ORDER BY PAYMENT_TIME DESC
FETCH FIRST 10 ROWS ONLY;
```

Taxpayer station:

```sql
SELECT t.TAXPAYER_ID,
       t.TAXPAYER_NAME,
       t.STATION_ID,
       s.STATION_NAME,
       t.UPDATED_AT
FROM CDC_APP.TAXPAYER t
LEFT JOIN CDC_APP.STATION s
  ON s.STATION_ID = t.STATION_ID
ORDER BY t.TAXPAYER_ID;
```

### Important SQL*Plus input note

Enter write statements and `COMMIT;` separately and wait for confirmation. Large pasted blocks previously caused SQL*Plus to concatenate statements unexpectedly.

Preferred:

```sql
UPDATE ...;
```

wait for success, then:

```sql
COMMIT;
```

---

## 4. Debezium / Kafka Connect

### Worker health

```bash
curl -s http://localhost:8083/
```

### Installed connector plugins

```bash
curl -s http://localhost:8083/connector-plugins | python -m json.tool
```

### Raw connector status

```bash
curl -s http://localhost:8083/connectors/oracle-cdc/status | python -m json.tool
```

### Flat connector status

```bash
curl -s http://localhost:8083/connectors/oracle-cdc-flat/status | python -m json.tool
```

Healthy connector/task state should show `RUNNING`.

### Resume connector

Raw:

```bash
curl -s -X PUT http://localhost:8083/connectors/oracle-cdc/resume
```

Flat:

```bash
curl -s -X PUT http://localhost:8083/connectors/oracle-cdc-flat/resume
```

### Oracle JDBC driver discovery in connector container

```bash
sudo docker exec poc-debezium sh -lc \
"find /kafka -type f \( -iname 'ojdbc*.jar' -o -iname 'xstreams*.jar' \) -print"
```

---

## 5. Validate Debezium connector config

Kafka Connect's validation endpoint expects a flat config map with `name` injected, not the outer `{name, config}` wrapper.

Raw connector example:

```bash
curl -s \
 -X PUT \
 -H "Content-Type: application/json" \
 --data "$(python -c "import json; d=json.load(open('debezium/oracle-cdc.json')); c=d['config']; c['name']=d['name']; print(json.dumps(c))")" \
 http://localhost:8083/connector-plugins/io.debezium.connector.oracle.OracleConnector/config/validate \
 | python -c "
import sys,json
d=json.load(sys.stdin)
print('error_count =', d['error_count'])
for x in d['configs']:
    errs=(x.get('value') or {}).get('errors', [])
    if errs:
        print(x['definition']['name'], ':', *errs)
"
```

Use the same pattern for the flat connector filename.

Do not commit the credential-bearing connector JSON files.

---

## 6. Kafka topics

List topics:

```bash
sudo docker exec poc-kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:19092 \
  --list
```

Important topics include:

```text
oraclecdc.CDC_APP.PAYMENT
oraclecdc.CDC_APP.TAXPAYER
oraclecdc.CDC_APP.STATION
oracleflat.CDC_APP.PAYMENT
oracleflat.CDC_APP.TAXPAYER
oracleflat.CDC_APP.STATION
```

---

## 7. Kafka console consumer

Example flat payment inspection:

```bash
sudo docker exec poc-kafka \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:19092 \
  --topic oracleflat.CDC_APP.PAYMENT \
  --from-beginning \
  --max-messages 10
```

For deeper raw-envelope inspection, consume:

```text
oraclecdc.CDC_APP.PAYMENT
```

Kafbat is normally more convenient for interactive inspection.

---

## 8. Kafka lag

Payment consumer group:

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe \
 --group clickhouse-oracle-payment-poc-v1
```

Taxpayer:

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe \
 --group clickhouse-oracle-taxpayer-poc-v1
```

Station:

```bash
sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe \
 --group clickhouse-oracle-station-poc-v1
```

For live monitoring:

```bash
watch -n 2 'sudo docker exec poc-kafka \
 /opt/kafka/bin/kafka-consumer-groups.sh \
 --bootstrap-server kafka:19092 \
 --describe --group clickhouse-oracle-payment-poc-v1'
```

Healthy steady state should normally converge to lag 0.

---

## 9. Kafka offset reset for a new/replay consumer group

Only use this intentionally.

Example:

```bash
sudo docker exec poc-kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --reset-offsets \
  --group clickhouse-oracle-payment-poc-v1 \
  --topic oracleflat.CDC_APP.PAYMENT \
  --to-earliest \
  --execute
```

Reset offsets before attaching/starting a consumer if the objective is explicitly to replay the existing topic backlog.

Do not reset offsets casually on an active consumer group.

---

## 10. ClickHouse

### CLI

```bash
sudo docker exec -it poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --database analytics
```

Use Ctrl+D to exit the ClickHouse client.

### Basic health query

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --query 'SELECT 1'
```

### Current payments

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query '
SELECT payment_id,
       taxpayer_id,
       amount,
       status,
       payment_time,
       latest_event_version
FROM fact_oracle_payment_current
ORDER BY payment_time DESC
LIMIT 20
'
```

### Serving view

```bash
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query '
SELECT payment_id,
       taxpayer_id,
       taxpayer_name,
       amount,
       payment_status,
       payment_time,
       station_at_payment,
       current_station
FROM vw_oracle_payment_analytics
ORDER BY payment_time DESC
LIMIT 20
'
```

### Live count/latest payment

```bash
watch -n 2 'sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query "
SELECT count() AS payments,
       sum(amount) AS total_amount,
       max(payment_time) AS latest_payment
FROM fact_oracle_payment_current
"'
```

---

## 11. Simulator — manual commands

Activate the project virtual environment if required, then export source database variables.

Examples:

```bash
python simulator/oracle_simulator.py show-taxpayer --taxpayer TIN001
```

Create payment:

```bash
python simulator/oracle_simulator.py \
  payment \
  --id PAY104 \
  --taxpayer TIN001 \
  --amount 810000 \
  --status SUCCESSFUL
```

The simulator must write only to Oracle.

---

## 12. Continuous simulator

Foreground:

```bash
python simulator/run_load.py --transactions-per-minute 10
```

Detached:

```bash
nohup python -u simulator/run_load.py \
  --transactions-per-minute 10 \
  > simulator/load.log 2>&1 &
echo $!
```

Tail log:

```bash
tail -f simulator/load.log
```

Stop tail with Ctrl+C.

Stop simulator:

```bash
pkill -f 'simulator/run_load.py'
```

Verify:

```bash
pgrep -af run_load.py
```

Use unbuffered Python (`-u`) for detached runs so the log updates promptly.

---

## 13. Kafbat

Open from an allowed browser host:

```text
http://10.1.78.38:8080
```

Use it to inspect:

- topics
- partitions
- raw events
- flattened events
- consumer groups
- offsets

The future application Event Monitor is not intended to replace Kafbat's deep Kafka view.

---

## 14. Future FastAPI application

Development command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Detached during early development if needed:

```bash
nohup uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  > fastapi.log 2>&1 &
```

Once stable, use systemd rather than relying on `nohup`.

Target URL:

```text
http://10.1.78.38:8000
```

---

## 15. Planned systemd operation

Expected commands once the service exists:

```bash
sudo systemctl start cdc-demo
sudo systemctl stop cdc-demo
sudo systemctl restart cdc-demo
sudo systemctl status cdc-demo
```

Logs:

```bash
journalctl -u cdc-demo -f
```

The service should use automatic restart and a protected environment file for credentials.

---

## 16. Quick full-stack health sequence

```bash
sudo docker compose ps
curl -s http://localhost:8083/connectors/oracle-cdc-flat/status | python -m json.tool
sudo docker exec poc-kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:19092 \
  --describe --group clickhouse-oracle-payment-poc-v1
sudo docker exec poc-clickhouse clickhouse-client \
  --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --database analytics \
  --query 'SELECT count(), max(payment_time) FROM fact_oracle_payment_current'
```

If these are healthy, the pipeline is usually ready for a source transaction test.
