import os
from decimal import Decimal
from typing import Optional, Tuple

import psycopg


def find_bill(subscriber_no: str, month: int, year: int) -> Optional[Tuple[Decimal, Decimal]]:
    with connect_billing() as connection:
        return connection.execute(
            """
            SELECT total_amount, paid_amount
            FROM bills
            WHERE subscriber_no = %s AND month = %s AND year = %s
            """,
            (subscriber_no, month, year),
        ).fetchone()


def connect_billing():
    return psycopg.connect(os.getenv("DATABASE_URL", "dbname=billing"))


def find_detailed_bill(subscriber_no: str, month: int, year: int):
    with connect_billing() as connection:
        return connection.execute(
            """
            SELECT total_amount, paid_amount, billed_phone_minutes, billed_internet_mb
            FROM bills
            WHERE subscriber_no = %s AND month = %s AND year = %s
            """,
            (subscriber_no, month, year),
        ).fetchone()


def lock_monthly_usage(connection, subscriber_no, month, year):
    return connection.execute(
        """
        SELECT phone_minutes, internet_mb
        FROM monthly_usage
        WHERE subscriber_no = %s AND month = %s AND year = %s
        FOR UPDATE
        """,
        (subscriber_no, month, year),
    ).fetchone()


def save_bill_total(
    connection, subscriber_no, month, year, total_amount, phone_minutes, internet_mb
) -> bool:
    return connection.execute(
        """
        INSERT INTO bills (
            subscriber_no, month, year, total_amount, paid_amount,
            billed_phone_minutes, billed_internet_mb
        )
        VALUES (%s, %s, %s, %s, 0, %s, %s)
        ON CONFLICT (subscriber_no, month, year) DO UPDATE
        SET total_amount = EXCLUDED.total_amount,
            billed_phone_minutes = EXCLUDED.billed_phone_minutes,
            billed_internet_mb = EXCLUDED.billed_internet_mb
        WHERE bills.paid_amount <= EXCLUDED.total_amount
        RETURNING total_amount
        """,
        (subscriber_no, month, year, total_amount, phone_minutes, internet_mb),
    ).fetchone() is not None


def lock_bill(connection, subscriber_no, month, year):
    return connection.execute(
        """
        SELECT total_amount, paid_amount
        FROM bills
        WHERE subscriber_no = %s AND month = %s AND year = %s
        FOR UPDATE
        """,
        (subscriber_no, month, year),
    ).fetchone()


def insert_payment(connection, transaction_id, subscriber_no, month, year, amount) -> bool:
    return connection.execute(
        """
        INSERT INTO bill_payments (transaction_id, subscriber_no, month, year, amount)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (transaction_id) DO NOTHING
        RETURNING transaction_id
        """,
        (transaction_id, subscriber_no, month, year, amount),
    ).fetchone() is not None


def update_bill_payment(connection, subscriber_no, month, year, paid_amount):
    connection.execute(
        """
        UPDATE bills SET paid_amount = %s
        WHERE subscriber_no = %s AND month = %s AND year = %s
        """,
        (paid_amount, subscriber_no, month, year),
    )
