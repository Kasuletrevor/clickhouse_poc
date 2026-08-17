from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "clickhouse/sql/efris_esb/001_schema.sql"
START = ROOT / "clickhouse/sql/efris_esb/002_start_consumer.sql"
KAFKA = ROOT / "scripts/configure_efris_esb_topic.sh"
VERIFY = ROOT / "scripts/verify_efris_esb_stream.sh"
BOOTSTRAP = ROOT / "scripts/bootstrap_efris_esb_consumer.sh"


def test_clickhouse_schema_contract():
    sql = SCHEMA.read_text()

    # Storage + queue
    assert "analytics.raw_efris_esb" in sql
    assert "analytics.efris_event" in sql
    assert "analytics.efris_esb_kafka_queue" in sql
    assert "EAI_Efris" in sql
    assert "clickhouse-efris-esb-poc-v1" in sql
    assert "kafka_format = 'RawBLOB'" in sql
    assert "INTERVAL 7 DAY" in sql

    # Parsing contract
    assert "isValidJSON" in sql
    assert "dataExchangeId" in sql
    assert "returnCode" in sql
    assert "= '00'" in sql
    assert "content_present" in sql
    assert "content_bytes" in sql
    assert "content_encrypted" in sql

    # Consumption/query layer
    assert "analytics.dim_efris_interface" in sql
    assert "analytics.v_efris_transactions" in sql
    assert "analytics.v_efris_success_transactions" in sql
    assert "analytics.v_efris_error_transactions" in sql
    assert "analytics.v_efris_observed_return_codes" in sql
    assert "analytics.v_efris_esb_invalid_messages" in sql


def test_business_views_filter_before_final_join():
    sql = SCHEMA.read_text()

    success_start = sql.index(
        "CREATE VIEW IF NOT EXISTS analytics.v_efris_success_transactions AS"
    )
    error_start = sql.index(
        "CREATE VIEW IF NOT EXISTS analytics.v_efris_error_transactions AS"
    )
    invalid_start = sql.index(
        "CREATE VIEW IF NOT EXISTS analytics.v_efris_esb_invalid_messages AS"
    )

    success_sql = sql[success_start:error_start]
    error_sql = sql[error_start:invalid_start]

    assert "FROM analytics.v_efris_transactions" not in success_sql
    assert "FROM analytics.efris_event FINAL" in success_sql
    assert "WHERE is_success = 1" in success_sql
    assert "LEFT JOIN" in success_sql
    assert success_sql.index("WHERE is_success = 1") < success_sql.index("LEFT JOIN")

    assert "FROM analytics.v_efris_transactions" not in error_sql
    assert "FROM analytics.efris_event FINAL" in error_sql
    assert "WHERE is_success = 0" in error_sql
    assert "LEFT JOIN" in error_sql
    assert error_sql.index("WHERE is_success = 0") < error_sql.index("LEFT JOIN")


def test_start_consumer_preserves_kafka_lineage():
    sql = START.read_text()
    assert "efris_esb_kafka_to_raw_mv" in sql
    assert "_topic" in sql
    assert "_partition" in sql
    assert "_offset" in sql
    assert "_timestamp_ms" in sql


def test_bootstrap_does_not_mutate_server_config_or_restart_clickhouse():
    script = BOOTSTRAP.read_text()
    assert "docker restart" not in script
    assert "docker cp" not in script
    assert "/etc/clickhouse-server/config.d" not in script
    assert "kafka-consumer-groups.sh" in script
    assert "clickhouse-efris-esb-poc-v1" in script


def test_kafka_policy_is_topic_scoped_and_seven_days():
    script = KAFKA.read_text()
    assert "EAI_Efris" in script
    assert "--entity-type topics" in script
    assert "retention.ms=604800000" in script
    assert "retention.bytes=-1" in script
    assert "cleanup.policy=delete" in script
    assert "segment.ms=3600000" in script
    assert "--partitions" not in script


def test_verifier_checks_offsets_tables_and_views():
    script = VERIFY.read_text()
    assert "kafka-get-offsets" in script
    assert "kafka-consumer-groups" in script
    assert "raw_efris_esb" in script
    assert "efris_event" in script
    assert "v_efris_transactions" in script
    assert "v_efris_success_transactions" in script
    assert "v_efris_error_transactions" in script
