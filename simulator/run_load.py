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

    # realistic-ish payment amounts
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

    # Mostly successful, but some pending transactions
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


def run(transactions_per_minute):
    if not DB_PASSWORD:
        raise RuntimeError("CDC_APP_PASSWORD is not set")

    interval = 60 / transactions_per_minute

    print()
    print("CDC SOURCE SYSTEM SIMULATOR")
    print("===========================")
    print(f"Rate     : {transactions_per_minute} transactions/min")
    print(f"Interval : approximately {interval:.1f} seconds")
    print(f"Oracle   : {DB_DSN}")
    print()
    print("Ctrl+C to stop.")
    print()

    counter = 1

    with connect() as conn:

        while running:
            try:
                #
                # Business event distribution:
                #
                # 80% new payment
                # 15% pending -> successful update
                #  5% taxpayer station movement
                #
                action = random.choices(
                    ["payment", "complete", "move"],
                    weights=[80, 15, 5],
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

            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="Continuous Oracle workload for CDC POC"
    )

    parser.add_argument(
        "--transactions-per-minute",
        type=float,
        default=10,
    )

    args = parser.parse_args()

    run(args.transactions_per_minute)


if __name__ == "__main__":
    main()
