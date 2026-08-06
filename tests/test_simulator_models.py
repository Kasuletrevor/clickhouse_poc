from datetime import datetime, timezone

from app.simulator.models import RunConfig, make_run_identity


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
