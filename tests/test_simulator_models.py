from datetime import datetime, timezone

from app.simulator.models import RunConfig, RunRecord, make_run_identity


def test_finite_config_has_exact_target_event_count():
    assert RunConfig(14.0, 60, 0.12, 1).target_events == 840
    assert RunConfig(14.0, 600, 0.12, 1).target_events == 8400


def test_continuous_config_has_no_target_event_count():
    assert RunConfig(14.0, 0, 0.12, 1).target_events is None


def test_run_identity_is_traceable_and_source_ids_fit_oracle_column():
    run_id, prefix = make_run_identity(datetime(2026, 8, 6, 8, 47, 1, tzinfo=timezone.utc), "A1")
    assert run_id == "EFR-20260806-084701-A1"
    assert prefix == "S260806A1"
    assert len(f"{prefix}-999999") <= 32


def test_cdc_gap_is_a_valid_terminal_run_state():
    run = RunRecord(
        "EFR-GAP",
        "S260813LF",
        "cdc_gap",
        "stop",
        14,
        300,
        4200,
        0.12,
        1,
        generated=4200,
        gap_events=236,
        gap_oracle_committed=4200,
        gap_clickhouse_received=3964,
        gap_reason="cdc_continuity_lost",
    )
    assert run.status == "cdc_gap"
    assert run.gap_events == 236
