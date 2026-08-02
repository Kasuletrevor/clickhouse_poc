import argparse
import os
from datetime import datetime

import oracledb


DB_USER = os.getenv("CDC_APP_USER", "CDC_APP")
DB_PASSWORD = os.getenv("CDC_APP_PASSWORD")
DB_DSN = os.getenv("CDC_APP_DSN", "localhost:1521/FREEPDB1")


def connect():
    if not DB_PASSWORD:
        raise RuntimeError(
            "CDC_APP_PASSWORD is not set. "
            "Export it before running the simulator."
        )

    return oracledb.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        dsn=DB_DSN,
    )


def create_payment(payment_id, taxpayer_id, amount, status):
    with connect() as conn:
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
                payment_id=payment_id,
                taxpayer_id=taxpayer_id,
                amount=amount,
                status=status,
            )

        conn.commit()

    print()
    print("PAYMENT COMMITTED TO ORACLE")
    print("---------------------------")
    print(f"payment_id : {payment_id}")
    print(f"taxpayer   : {taxpayer_id}")
    print(f"amount     : {amount}")
    print(f"status     : {status}")
    print(f"client time: {datetime.now()}")


def move_taxpayer(taxpayer_id, station_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE TAXPAYER
                SET
                    STATION_ID = :station_id,
                    UPDATED_AT = SYSTIMESTAMP
                WHERE TAXPAYER_ID = :taxpayer_id
                """,
                station_id=station_id,
                taxpayer_id=taxpayer_id,
            )

            if cur.rowcount != 1:
                conn.rollback()
                raise RuntimeError(
                    f"Expected one taxpayer, updated {cur.rowcount}"
                )

        conn.commit()

    print()
    print("TAXPAYER CHANGE COMMITTED TO ORACLE")
    print("-----------------------------------")
    print(f"taxpayer   : {taxpayer_id}")
    print(f"new station: {station_id}")
    print(f"client time: {datetime.now()}")


def show_taxpayer(taxpayer_id):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    TAXPAYER_ID,
                    TAXPAYER_NAME,
                    TAXPAYER_TYPE,
                    STATION_ID,
                    UPDATED_AT
                FROM TAXPAYER
                WHERE TAXPAYER_ID = :taxpayer_id
                """,
                taxpayer_id=taxpayer_id,
            )

            row = cur.fetchone()

    if row is None:
        print("Taxpayer not found.")
        return

    print()
    print("ORACLE TAXPAYER")
    print("----------------")
    print(f"taxpayer_id   : {row[0]}")
    print(f"name          : {row[1]}")
    print(f"type          : {row[2]}")
    print(f"station_id    : {row[3]}")
    print(f"updated_at    : {row[4]}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Oracle source-system simulator for CDC POC"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    payment = sub.add_parser("payment")
    payment.add_argument("--id", required=True)
    payment.add_argument("--taxpayer", required=True)
    payment.add_argument("--amount", required=True, type=float)
    payment.add_argument(
        "--status",
        default="SUCCESSFUL",
        choices=["PENDING", "SUCCESSFUL", "REVERSED"],
    )

    move = sub.add_parser("move-taxpayer")
    move.add_argument("--taxpayer", required=True)
    move.add_argument("--station", required=True)

    show = sub.add_parser("show-taxpayer")
    show.add_argument("--taxpayer", required=True)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "payment":
        create_payment(
            args.id,
            args.taxpayer,
            args.amount,
            args.status,
        )

    elif args.command == "move-taxpayer":
        move_taxpayer(
            args.taxpayer,
            args.station,
        )

    elif args.command == "show-taxpayer":
        show_taxpayer(args.taxpayer)


if __name__ == "__main__":
    main()
