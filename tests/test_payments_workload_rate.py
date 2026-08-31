from simulator import run_load


def test_events_per_second_is_converted_to_subsecond_interval():
    assert run_load.interval_for_rate(events_per_second=10) == 0.1


def test_workload_mix_weights_are_editable():
    assert run_load.workload_weights(70, 20, 10) == [70.0, 20.0, 10.0]


def test_workload_mix_must_total_100():
    try:
        run_load.workload_weights(70, 20, 5)
    except ValueError as exc:
        assert "100" in str(exc)
    else:
        raise AssertionError("Expected an invalid workload mix to be rejected")
