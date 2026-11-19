import bill_repository


class SubscriberNotFound(Exception):
    pass


class TotalBelowPaidAmount(Exception):
    pass


class BillNotFound(Exception):
    pass


class DuplicateTransaction(Exception):
    pass


class PaymentExceedsBalance(Exception):
    pass


def query_bill(subscriber_no: str, month: int, year: int):
    bill = bill_repository.find_bill(subscriber_no, month, year)
    if bill is None:
        return None
    return bill_summary(subscriber_no, month, year, *bill)


def bill_summary(subscriber_no, month, year, total_amount, paid_amount):
    remaining_balance = total_amount - paid_amount
    if remaining_balance == 0:
        status = "paid"
    elif paid_amount == 0:
        status = "unpaid"
    else:
        status = "partially_paid"

    return {
        "subscriber_no": subscriber_no,
        "month": month,
        "year": year,
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "remaining_balance": remaining_balance,
        "status": status,
    }


def tariff_charges(phone_minutes: int, internet_mb: int) -> dict[str, int]:
    extra_minutes = max(phone_minutes - 1_000, 0)
    extra_mb = max(internet_mb - 20_000, 0)
    return {
        "internet_base": 50,
        "phone_overage": 10 * ((extra_minutes + 999) // 1_000),
        "internet_overage": 10 * ((extra_mb + 9_999) // 10_000),
    }


def query_detailed_bill(subscriber_no, month, year, page, page_size):
    bill = bill_repository.find_detailed_bill(subscriber_no, month, year)
    if bill is None:
        return None

    total_amount, paid_amount, phone_minutes, internet_mb = bill
    if phone_minutes is None or internet_mb is None:
        charges = {"unitemized": total_amount}
    else:
        charges = tariff_charges(phone_minutes, internet_mb)

    items = [{"type": charge_type, "amount": amount} for charge_type, amount in charges.items()]
    start = (page - 1) * page_size
    return {
        **bill_summary(subscriber_no, month, year, total_amount, paid_amount),
        "phone_minutes": phone_minutes,
        "internet_mb": internet_mb,
        "internet_gb": internet_mb / 1_000 if internet_mb is not None else None,
        "charges": items[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total_items": len(items),
    }


def calculate_bill(subscriber_no: str, month: int, year: int) -> None:
    with bill_repository.connect_billing() as connection:
        usage = bill_repository.lock_monthly_usage(connection, subscriber_no, month, year)
        if usage is None:
            if not bill_repository.subscriber_exists(connection, subscriber_no):
                raise SubscriberNotFound
            usage = (0, 0)

        phone_minutes, internet_mb = usage
        total_amount = sum(tariff_charges(phone_minutes, internet_mb).values())
        if not bill_repository.save_bill_total(
            connection, subscriber_no, month, year, total_amount, phone_minutes, internet_mb
        ):
            raise TotalBelowPaidAmount


def pay_bill(subscriber_no, month, year, amount, transaction_id):
    with bill_repository.connect_billing() as connection:
        bill = bill_repository.lock_bill(connection, subscriber_no, month, year)
        if bill is None:
            raise BillNotFound
        total_amount, paid_amount = bill

        if not bill_repository.insert_payment(
            connection, transaction_id, subscriber_no, month, year, amount
        ):
            raise DuplicateTransaction

        new_paid_amount = paid_amount + amount
        if new_paid_amount > total_amount:
            raise PaymentExceedsBalance
        bill_repository.update_bill_payment(connection, subscriber_no, month, year, new_paid_amount)

    return {
        "status": "success",
        "paid_amount": new_paid_amount,
        "remaining_balance": total_amount - new_paid_amount,
    }
