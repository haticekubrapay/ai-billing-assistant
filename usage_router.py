import os
from secrets import compare_digest
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field


router = APIRouter()
usage_bearer = HTTPBearer(auto_error=False)


class UsageRequest(BaseModel):
    subscriber_no: str = Field(min_length=1)
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=1, le=9999)
    usage_type: Literal["Phone", "Internet"]


def require_usage_operator(
    credentials: HTTPAuthorizationCredentials = Depends(usage_bearer),
) -> None:
    token = os.getenv("USAGE_OPERATOR_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Usage authorization is not configured.")
    if credentials is None or not compare_digest(
        credentials.credentials.encode(), token.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing operator token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/api/v1/usage", dependencies=[Depends(require_usage_operator)])
def add_usage(usage: UsageRequest):
    phone_minutes, internet_mb = (10, 0) if usage.usage_type == "Phone" else (0, 1)
    database_url = os.getenv("DATABASE_URL", "dbname=billing")
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO monthly_usage (subscriber_no, month, year, phone_minutes, internet_mb)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (subscriber_no, month, year) DO UPDATE
            SET phone_minutes = monthly_usage.phone_minutes + EXCLUDED.phone_minutes,
                internet_mb = monthly_usage.internet_mb + EXCLUDED.internet_mb
            """,
            (usage.subscriber_no, usage.month, usage.year, phone_minutes, internet_mb),
        )

    return {"status": "success"}
