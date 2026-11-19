from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StrictBool

from bill_service import (
    BillNotFound,
    DuplicateTransaction,
    PaymentExceedsBalance,
    TotalBelowPaidAmount,
    SubscriberNotFound,
    calculate_bill,
    pay_bill,
    query_bill,
    query_detailed_bill,
)
from usage_router import require_usage_operator


router = APIRouter()


class BillPeriod(BaseModel):
    subscriber_no: str = Field(min_length=1)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=1, le=9999)


class PayBillRequest(BillPeriod):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    transaction_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    confirmed: StrictBool


@router.post("/api/v1/bills/calculate", dependencies=[Depends(require_usage_operator)])
def calculate_bill_endpoint(period: BillPeriod):
    try:
        calculate_bill(period.subscriber_no, period.month, period.year)
    except SubscriberNotFound:
        raise HTTPException(status_code=404, detail="Subscriber not found.") from None
    except TotalBelowPaidAmount:
        raise HTTPException(
            status_code=409, detail="Calculated total cannot be lower than the paid amount."
        ) from None
    return {"status": "success"}


@router.post("/api/v1/bills/pay", dependencies=[Depends(require_usage_operator)])
def pay_bill_endpoint(payment: PayBillRequest):
    if not payment.confirmed:
        raise HTTPException(status_code=400, detail="Payment confirmation is required.")
    try:
        return pay_bill(
            payment.subscriber_no, payment.month, payment.year,
            payment.amount, payment.transaction_id,
        )
    except BillNotFound:
        raise HTTPException(status_code=404, detail="Bill not found.") from None
    except DuplicateTransaction:
        raise HTTPException(status_code=409, detail="Transaction ID already exists.") from None
    except PaymentExceedsBalance:
        raise HTTPException(status_code=409, detail="Payment exceeds remaining balance.") from None


@router.get("/api/v1/bills/{subscriber_no}")
def get_bill(subscriber_no: str, year: int, month: int = Query(..., ge=1, le=12)):
    bill = query_bill(subscriber_no, month, year)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    return bill


@router.get(
    "/api/v1/bills/{subscriber_no}/details",
    dependencies=[Depends(require_usage_operator)],
)
def get_bill_details(
    subscriber_no: str,
    year: int = Query(..., ge=1, le=9999),
    month: int = Query(..., ge=1, le=12),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    bill = query_detailed_bill(subscriber_no, month, year, page, page_size)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    return bill
