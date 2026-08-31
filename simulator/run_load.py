import argparse
import os
import random
import signal
import time
from datetime import datetime

import oracledb


DB_USER = os.getenv("CDC_APP_USER", "CDC_APP")
DB_PASSWORD = os.getenv("CDC_APP_PASSWORD")
DB_DSN = os.getenv("CDC_APP_DSN", "localhost:1521/FREEPDB1")

TAXPAYERS = ["TIN001", "TIN002", "TIN003"]
STATIONS = ["ST001", "ST002", "ST003"]

running = True


def stop_handler(signum, frame):
    global running
    print("\nStopping simulator...")
    running = False


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def interval_for_rate(events_per_second=None, transactions_per_minute=None):
    if events_per_second is not None:
        rate = float(events_per_second)
        if rate <= 0:
            raise ValueError("events_per_second must be greater than zero")
        return 1.0 / rate

    if transactions_per_minute is not None:
        rate = float(transactions_per_minute)
        if rate <= 0:
            raise ValueError("transactions_per_minute must be greater than zero")
        return 60.0 / rate

    raise ValueError("A workload rate is required")


def workload_weights(payment_create_pct=80, status_update_pct=15, taxpayer_move_pct=5):
    weights = [
        float(payment_create_pct),
        float(status_update_pct),
        float(taxpayer_move_pct),
    ]
    if any(weight < 0 for weight in weights):
        raise ValueError("Workload mix percentages cannot be negative")
    if abs(sum(weights) - 100.0) > 1e-6:
        raise ValueError("Workload mix percentages must total 100")
    return weights


def connect():
    return oracledb.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        dsn=DB_DSN,
    )


def payment_id(counter):
    # <= 20 chars and easy to recognize in the demo
    return f"SIM{datetime.now():%H%M%S}{counter:04d}"


def create_payment(conn, counter):
    taxpayer = random.choice(TAXPAYERS)

    amount = random.choice([
        150000,
        250000,
        400000,
        500000,
        750000,
        1000000,
        1250000,
        1500000,
        2000000,
        2500000,
    ])

    status = random.choices(
        ["SUCCESSFUL", "PENDING"],
        weights=[85, 15],
        k=1,
    )[0]

    pid = payment_id(counter)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO PAYMENT
            (
                PAYMENT_ID,
                TAXPAYER_ID,
                AMOUNT,
                STATUS,
                PAYMENT_TIME,
                UPDATED_AT
            )
            VALUES
            (
                :payment_id,
                :taxpayer_id,
                :amount,
                :status,
                SYSTIMESTAMP,
                SYSTIMESTAMP
            )
            """,
            payment_id=pid,
            taxpayer_id=taxpayer,
            amount=amount,
            status=status,
        )

    conn.commit()

    print(
        f"[PAYMENT] {pid} | "
        f"{taxpayer} | "
        f"{amount:,.0f} | "
        f"{status}"
    )

    return pid, status


def complete_pending_payment(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT PAYMENT_ID
            FROM
            (
                SELECT PAYMENT_ID
                FROM PAYMENT
                WHERE STATUS = 'PENDING'
                ORDER BY PAYMENT_TIME
            )
            WHERE ROWNUM = 1
            """
        )

        row = cur.fetchone()

        if not row:
            return False

        pid = row[0]

        cur.execute(
            """
            UPDATE PAYMENT
            SET
                STATUS = 'SUCCESSFUL',
                UPDATED_AT = SYSTIMESTAMP
            WHERE PAYMENT_ID = :payment_id
            """,
            payment_id=pid,
        )

    conn.commit()

    print(f"[UPDATE ] {pid} | PENDING -> SUCCESSFUL")

    return True


def move_taxpayer(conn):
    taxpayer = random.choice(TAXPAYERS)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT STATION_ID
            FROM TAXPAYER
            WHERE TAXPAYER_ID = :taxpayer
            """,
            taxpayer=taxpayer,
        )

        current_station = cur.fetchone()[0]

        possible = [
            station
            for station in STATIONS
            if station != current_station
        ]

        new_station = random.choice(possible)

        cur.execute(
            """
            UPDATE TAXPAYER
            SET
                STATION_ID = :station,
                UPDATED_AT = SYSTIMESTAMP
            WHERE TAXPAYER_ID = :taxpayer
            """,
            station=new_station,
            taxpayer=taxpayer,
        )

    conn.commit()

    print(
        f"[MOVE   ] {taxpayer} | "
        f"{current_station} -> {new_station}"
    )


def run(
    events_per_second=None,
    transactions_per_minute=None,
    payment_create_pct=80,
    status_update_pct=15,
    taxpayer_move_pct=5,
):
    global running
    running = True

    if not DB_PASSWORD:
        raise RuntimeError("CDC_APP_PASSWORD is not set")

    interval = interval_for_rate(
        events_per_second=events_per_second,
        transactions_per_minute=transactions_per_minute,
    )
    weights = workload_weights(
        payment_create_pct,
        status_update_pct,
        taxpayer_move_pct,
    )

    if events_per_second is not None:
        rate_label = f"{float(events_per_second):g} events/sec"
    else:
        rate_label = f"{float(transactions_per_minute):g} transactions/min"

    print()
    print("CDC SOURCE SYSTEM SIMULATOR")
    print("===========================")
    print(f"Rate     : {rate_label}")
    print(f"Interval : approximately {interval:.4f} seconds")
    print(
        "Mix      : "
        f"{weights[0]:g}% payment / "
        f"{weights[1]:g}% status update / "
        f"{weights[2]:g}% taxpayer move"
    )
    print(f"Oracle   : {DB_DSN}")
    print()
    print("Ctrl+C to stop.")
    print()

    counter = 1
    next_event_at = time.monotonic()

    with connect() as conn:
        while running:
            try:
                action = random.choices(
                    ["payment", "complete", "move"],
                    weights=weights,
                    k=1,
                )[0]

                if action == "payment":
                    create_payment(conn, counter)
                    counter += 1

                elif action == "complete":
                    if not complete_pending_payment(conn):
                        create_payment(conn, counter)
                        counter += 1

                elif action == "move":
                    move_taxpayer(conn)

            except Exception as exc:
                print(f"[ERROR  ] {exc}")

                try:
                    conn.rollback()
                except Exception:
                    pass

            next_event_at += interval
            sleep_for = next_event_at - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_event_at = time.monotonic()


def main():
    parser = argparse.ArgumentParser(
        description="Continuous Oracle workload for CDC POC"
    )

    rate_group = parser.add_mutually_exclusive_group()
    rate_group.add_argument(
        "--transactions-per-second",
        type=float,
        default=None,
    )
    rate_group.add_argument(
        "--transactions-per-minute",
        type=float,
        default=None,
    )

    parser.add_argument("--payment-create-pct", type=float, default=80.0)
    parser.add_argument("--status-update-pct", type=float, default=15.0)
    parser.add_argument("--taxpayer-move-pct", type=float, default=5.0)

    args = parser.parse_args()

    events_per_second = args.transactions_per_second
    transactions_per_minute = args.transactions_per_minute
    if events_per_second is None and transactions_per_minute is None:
        transactions_per_minute = 10.0

    run(
        events_per_second=events_per_second,
        transactions_per_minute=transactions_per_minute,
        payment_create_pct=args.payment_create_pct,
        status_update_pct=args.status_update_pct,
        taxpayer_move_pct=args.taxpayer_move_pct,
    )


if __name__ == "__main__":
    main()
