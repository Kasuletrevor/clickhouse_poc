from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.config import get_settings
from app.oracle import OracleDatabase
from app.simulator.engine import EfrisEventFactory, INSERT_SQL, RatePacer
from app.simulator.models import utc_now_iso
from app.simulator.store import RunStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = PROJECT_ROOT / "simulation"


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: simulator source operation failed"


def run_worker(run_id: str) -> None:
    settings = get_settings()
    runtime_dir = Path(settings.simulator_runtime_dir)
    if not runtime_dir.is_absolute():
        runtime_dir = PROJECT_ROOT / runtime_dir
    store = RunStore(runtime_dir)
    record = store.get_run(run_id)
    started_mono = time.perf_counter()
    paused_total = float(record.paused_seconds)
    pause_started = None
    last_sample_time = started_mono
    last_sample_count = record.generated

    def active_elapsed(now: float) -> float:
        current_pause = (now - pause_started) if pause_started is not None else 0.0
        return max(0.0, now - started_mono - paused_total - current_pause)

    try:
        db = OracleDatabase(settings)
        factory = EfrisEventFactory(
            SIM_DIR,
            record.source_prefix,
            record.random_seed,
            record.retry_probability,
        )
        pacer = RatePacer(record.rate)
        with db.connection() as conn:
            with conn.cursor() as cursor:
                current = store.get_run(run_id)
                if current.command == "stop":
                    store.set_fields(
                        run_id,
                        status="draining",
                        active_elapsed_seconds=0.0,
                        last_heartbeat=utc_now_iso(),
                    )
                    return
                store.set_fields(run_id, status="running", last_heartbeat=utc_now_iso())
                while True:
                    current = store.get_run(run_id)
                    now = time.perf_counter()

                    if current.command == "stop":
                        store.set_fields(
                            run_id,
                            status="draining",
                            active_elapsed_seconds=active_elapsed(now),
                            last_heartbeat=utc_now_iso(),
                        )
                        break

                    if current.target_events is not None and current.generated >= current.target_events:
                        store.set_fields(
                            run_id,
                            status="draining",
                            active_elapsed_seconds=active_elapsed(now),
                            last_heartbeat=utc_now_iso(),
                        )
                        break

                    if current.command == "pause":
                        if pause_started is None:
                            pause_started = now
                            store.set_fields(
                                run_id,
                                status="paused",
                                active_elapsed_seconds=active_elapsed(now),
                                last_heartbeat=utc_now_iso(),
                            )
                        else:
                            store.set_fields(
                                run_id,
                                last_heartbeat=utc_now_iso(),
                                active_elapsed_seconds=active_elapsed(now),
                            )
                        time.sleep(0.2)
                        continue

                    if pause_started is not None:
                        paused_total += now - pause_started
                        pause_started = None
                        pacer.reset()
                        store.set_fields(
                            run_id,
                            status="running",
                            paused_seconds=paused_total,
                            last_heartbeat=utc_now_iso(),
                        )

                    pacer.wait_next()
                    current = store.get_run(run_id)
                    if current.command != "run":
                        continue
                    sequence = current.last_sequence + 1
                    bindings = factory.next_bindings(cursor, sequence)
                    try:
                        cursor.execute(INSERT_SQL, bindings)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise

                    now = time.perf_counter()
                    next_generated = current.generated + 1
                    samples = list(current.source_rate_samples)
                    if now - last_sample_time >= 1.0:
                        sample_elapsed = max(now - last_sample_time, 0.000001)
                        sample_rate = (next_generated - last_sample_count) / sample_elapsed
                        samples.append(
                            {
                                "at": utc_now_iso(),
                                "rate": round(sample_rate, 3),
                                "generated": next_generated,
                            }
                        )
                        samples = samples[-120:]
                        last_sample_time = now
                        last_sample_count = next_generated
                    store.set_fields(
                        run_id,
                        generated=next_generated,
                        last_sequence=sequence,
                        active_elapsed_seconds=active_elapsed(now),
                        paused_seconds=paused_total,
                        last_heartbeat=utc_now_iso(),
                        source_rate_samples=samples,
                    )
    except Exception as exc:
        current = store.get_run(run_id)
        store.set_fields(
            run_id,
            status="failed",
            failures=current.failures + 1,
            error=_safe_error(exc),
            finished_at=utc_now_iso(),
            last_heartbeat=utc_now_iso(),
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Detached EFRIS simulator worker")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_worker(args.run_id)


if __name__ == "__main__":
    main()
