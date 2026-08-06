from __future__ import annotations

import argparse
import json
import random
import sys
import time
import uuid
from collections import defaultdict, deque
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.oracle import OracleDatabase

SIM_DIR = ROOT / "simulation"


def load_json(name: str):
    with (SIM_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def weighted_choice(rng: random.Random, rows, weight_key="weight"):
    return rng.choices(rows, weights=[float(row.get(weight_key, 1)) for row in rows], k=1)[0]


def money(value: int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def vat_from_gross(gross: Decimal) -> Decimal:
    return (gross * Decimal("18") / Decimal("118")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def build_reference(cursor, tin: str) -> str:
    cursor.execute("SELECT SEQ_EFRIS_SELLER_REF.NEXTVAL FROM DUAL")
    value = int(cursor.fetchone()[0])
    return f"{tin}-INV-{value:08d}"


def source_id() -> str:
    return "SIMERR" + uuid.uuid4().hex[:26]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate EFRIS error-log source transactions in Oracle at a controlled rate."
    )
    parser.add_argument("--rate", type=float, help="Target error events per second.")
    parser.add_argument(
        "--duration",
        type=int,
        help="Run duration in seconds. Use 0 to continue until Ctrl+C.",
    )
    parser.add_argument("--seed", type=int, help="Random seed for this run.")
    args = parser.parse_args()

    config = load_json("config.json")
    taxpayers = load_json("generated_taxpayers.json")
    devices = load_json("generated_devices.json")
    error_codes = load_json("error_codes.json")
    products = load_json("products.json")

    rate = float(args.rate if args.rate is not None else config["target_events_per_second"])
    duration = int(args.duration if args.duration is not None else config["duration_seconds"])
    seed = int(args.seed if args.seed is not None else config["random_seed"])

    if rate <= 0:
        raise SystemExit("--rate must be greater than zero")
    if duration < 0:
        raise SystemExit("--duration cannot be negative")
    if not taxpayers or not devices or not error_codes:
        raise SystemExit("Simulation population is empty. Run scripts/seed_efris_population.py first.")

    rng = random.Random(seed)
    interval = 1.0 / rate
    report_interval = float(config["report_interval_seconds"])
    retry_probability = float(config["retry_probability"])
    recent_limit = int(config["recent_reference_pool"])
    gross_min = int(config["gross_amount_min"])
    gross_max = int(config["gross_amount_max"])
    currency = str(config["currency"])
    create_user_id = str(config["create_user_id"])

    devices_by_taxpayer = defaultdict(list)
    for device in devices:
        devices_by_taxpayer[device["taxpayer_id"]].append(device)

    recent = deque(maxlen=recent_limit)
    generated = 0
    failures = 0
    started = time.perf_counter()
    next_due = started
    next_report = started + report_interval

    insert_sql = """
        INSERT INTO T_INVOICE_ERROR_LOG
            (ID, TIN, DEVICE_NO, SELLER_REFERENCE_NO, RETURN_CODE, RETURN_MSG,
             GROSS_AMOUNT, TAX_AMOUNT, CURRENCY, ITEM_DESCRIPTION,
             CREATE_USER_ID, CREATE_DATE)
        VALUES
            (:source_id, :tin, :device_no, :seller_reference_no,
             :return_code, :return_msg, :gross_amount, :tax_amount,
             :currency, :item_description, :create_user_id, SYSDATE)
    """

    print("EFRIS error-log simulator")
    print(f"Target rate       : {rate:.2f} events/sec")
    print(f"Duration          : {'until Ctrl+C' if duration == 0 else str(duration) + ' sec'}")
    print(f"Taxpayers         : {len(taxpayers)}")
    print(f"Devices           : {len(devices)}")
    print(f"Error codes       : {len(error_codes)}")
    print(f"Retry probability : {retry_probability:.0%}")
    if duration:
        print(f"Expected events   : {round(rate * duration):,}")
    print()

    db = OracleDatabase(get_settings())

    try:
        with db.connection() as conn:
            with conn.cursor() as cursor:
                while True:
                    now = time.perf_counter()
                    elapsed = now - started
                    if duration and elapsed >= duration:
                        break

                    sleep_for = next_due - now
                    if sleep_for > 0:
                        time.sleep(sleep_for)

                    is_retry = bool(recent) and rng.random() < retry_probability

                    if is_retry:
                        previous = rng.choice(tuple(recent))
                        taxpayer = previous["taxpayer"]
                        device = previous["device"]
                        seller_reference_no = previous["seller_reference_no"]
                        gross_amount = previous["gross_amount"]
                        tax_amount = previous["tax_amount"]
                        item_description = previous["item_description"]
                    else:
                        taxpayer = weighted_choice(rng, taxpayers, "traffic_weight")
                        taxpayer_devices = devices_by_taxpayer[taxpayer["taxpayer_id"]]
                        if not taxpayer_devices:
                            failures += 1
                            next_due += interval
                            continue
                        device = weighted_choice(rng, taxpayer_devices, "traffic_weight")
                        seller_reference_no = build_reference(cursor, taxpayer["taxpayer_id"])
                        gross_amount = money(rng.randint(gross_min, gross_max))
                        tax_amount = vat_from_gross(gross_amount)
                        item_description = rng.choice(products)

                    error = weighted_choice(rng, error_codes)
                    return_message = str(error["message"])[:256]

                    try:
                        cursor.execute(
                            insert_sql,
                            {
                                "source_id": source_id(),
                                "tin": taxpayer["taxpayer_id"],
                                "device_no": device["device_no"],
                                "seller_reference_no": seller_reference_no,
                                "return_code": str(error["code"]),
                                "return_msg": return_message,
                                "gross_amount": gross_amount,
                                "tax_amount": tax_amount,
                                "currency": currency,
                                "item_description": item_description,
                                "create_user_id": create_user_id,
                            },
                        )
                        conn.commit()
                        generated += 1

                        if not is_retry:
                            recent.append(
                                {
                                    "taxpayer": taxpayer,
                                    "device": device,
                                    "seller_reference_no": seller_reference_no,
                                    "gross_amount": gross_amount,
                                    "tax_amount": tax_amount,
                                    "item_description": item_description,
                                }
                            )
                    except Exception:
                        conn.rollback()
                        failures += 1
                        raise

                    next_due += interval
                    now = time.perf_counter()
                    if now >= next_report:
                        runtime = now - started
                        actual_rate = generated / runtime if runtime else 0.0
                        schedule_lag_ms = max(0.0, (now - next_due) * 1000.0)
                        print(
                            f"generated={generated:,}  failures={failures:,}  "
                            f"actual={actual_rate:.2f}/s  schedule_lag={schedule_lag_ms:.1f}ms"
                        )
                        next_report = now + report_interval

    except KeyboardInterrupt:
        print("\nStopped by user.")

    runtime = time.perf_counter() - started
    actual_rate = generated / runtime if runtime else 0.0
    print()
    print("Simulation summary")
    print(f"Generated          : {generated:,}")
    print(f"Failures           : {failures:,}")
    print(f"Runtime            : {runtime:.2f} sec")
    print(f"Actual source rate : {actual_rate:.2f} events/sec")
    print("Source path        : Oracle only; Debezium/Kafka/ClickHouse are downstream CDC.")


if __name__ == "__main__":
    main()
