from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.oracle import OracleDatabase
from app.simulator.engine import EfrisEventFactory, INSERT_SQL, RatePacer, load_json
from app.simulator.models import RunConfig, make_run_identity

SIM_DIR = ROOT / "simulation"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EFRIS error-log source transactions in Oracle at a controlled rate.")
    parser.add_argument("--rate", type=float, help="Target error events per second.")
    parser.add_argument("--duration", type=int, help="Active generation duration in seconds. Use 0 for continuous mode.")
    parser.add_argument("--seed", type=int, help="Random seed for this run.")
    parser.add_argument("--source-prefix", help="Optional run source prefix for diagnostics (for example S260806A1).")
    args = parser.parse_args()

    defaults = load_json(SIM_DIR, "config.json")
    config = RunConfig(
        rate=float(args.rate if args.rate is not None else defaults["target_events_per_second"]),
        duration_seconds=int(args.duration if args.duration is not None else defaults["duration_seconds"]),
        retry_probability=float(defaults["retry_probability"]),
        random_seed=int(args.seed if args.seed is not None else defaults["random_seed"]),
    )
    run_id, generated_prefix = make_run_identity()
    source_prefix = args.source_prefix or generated_prefix
    factory = EfrisEventFactory(SIM_DIR, source_prefix, config.random_seed, config.retry_probability)
    pacer = RatePacer(config.rate)
    db = OracleDatabase(get_settings())

    print("EFRIS error-log simulator")
    print(f"Run ID            : {run_id}")
    print(f"Source prefix      : {source_prefix}")
    print(f"Target rate        : {config.rate:.2f} events/sec")
    print(f"Duration           : {'until Ctrl+C' if config.duration_seconds == 0 else str(config.duration_seconds) + ' sec'}")
    print(f"Retry probability  : {config.retry_probability:.0%}")
    if config.target_events is not None:
        print(f"Target events      : {config.target_events:,}")
    print()

    generated = 0
    failures = 0
    started = time.perf_counter()
    last_report = started

    try:
        with db.connection() as conn:
            with conn.cursor() as cursor:
                while config.target_events is None or generated < config.target_events:
                    lag = pacer.wait_next()
                    bindings = factory.next_bindings(cursor, generated + 1)
                    try:
                        cursor.execute(INSERT_SQL, bindings)
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        failures += 1
                        raise
                    generated += 1
                    now = time.perf_counter()
                    if now - last_report >= float(defaults.get("report_interval_seconds", 5)):
                        runtime = now - started
                        print(f"generated={generated:,} failures={failures:,} actual={generated/runtime:.2f}/s schedule_lag={lag*1000:.1f}ms")
                        last_report = now
    except KeyboardInterrupt:
        print("\nStopped by user.")

    runtime = time.perf_counter() - started
    print("\nSimulation summary")
    print(f"Generated          : {generated:,}")
    print(f"Failures           : {failures:,}")
    print(f"Runtime            : {runtime:.2f} sec")
    print(f"Actual source rate : {generated/runtime if runtime else 0.0:.2f} events/sec")
    print("Source path        : Oracle only; Debezium/Kafka/ClickHouse are downstream CDC.")


if __name__ == "__main__":
    main()
