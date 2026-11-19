# AI Billing Support Assistant

## Add Usage

`POST /api/v1/usage` takes a JSON body with `subscriber_no`, `month`, `year`,
and `usage_type`. `Phone` adds 10 minutes and `Internet` adds 1 MB to the
subscriber's total for that month. A successful request returns HTTP 200 with
`{"status":"success"}`. Each accepted request adds usage again.

The endpoint uses an operator bearer token from `USAGE_OPERATOR_TOKEN`. This
credential is for the trusted mobile provider operator, who can record usage
for any subscriber. Keep it out of source control and subscriber-facing clients.
Requests with missing or invalid credentials receive HTTP 401 when configured.
The endpoint returns HTTP 503 if the server has no token configured.

For the local setup, load the token from the private, ignored `.usage-token`
file when starting Uvicorn. In Swagger UI, select **Authorize** and paste the
token value. Apply `schema.sql` to the database before using the endpoint.

```sh
DATABASE_URL='host=/tmp dbname=billing' USAGE_OPERATOR_TOKEN="$(cat .usage-token)" \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## Calculate Bill

`POST /api/v1/bills/calculate` accepts `subscriber_no`, `month`, and `year`
in a JSON body and uses the same operator token as Add Usage. It returns
HTTP 200 with `{"status":"success"}` after saving the bill. Use Query Bill
to read the saved amount.

The first 1,000 phone minutes are free. Each started block of 1,000 extra
minutes costs $10. Internet costs $50 through 20 GB, plus $10 per started
extra 10 GB block (1 GB = 1,000 MB). The $50 base applies even in a month
with zero usage. If the selected month has no usage record, the bill uses zero
phone minutes and zero MB for a subscriber with an existing usage or bill
record. This project uses those records to identify known subscribers. A
subscriber with neither record receives HTTP 404.
Recalculation preserves payments and returns HTTP 409 if
the new total would be lower than the amount already paid.

## Query Bill Detailed

`GET /api/v1/bills/{subscriber_no}/details` requires the operator token and
the `month` and `year` query parameters. It returns the bill summary, billed
phone minutes, billed internet in MB and GB, and a page of charge items.
`page` starts at 1. `page_size` defaults to 10 and accepts 1 through 100.
`total_items` is the number of charge items across all pages.

Apply `schema.sql` before deploying the updated API. Calculate Bill now
saves the usage used to calculate each invoice. Usage added afterward shows
up in the invoice details after recalculation. Existing invoices without
recorded billed usage return null usage and a single `unitemized` charge
equal to the stored bill total.

## Pay Bill

`POST /api/v1/bills/pay` simulates a partial or full payment. In Swagger,
authorize with the operator token and send `subscriber_no`, `month`, `year`,
`amount`, a unique `transaction_id`, and `confirmed: true` after explicitly
confirming the payment. Amounts must be positive and have at most two decimal
places. The transaction ID is case-sensitive and may contain letters, digits,
hyphens, or underscores.

The response includes the transaction status, cumulative `paid_amount`, and
`remaining_balance`. Duplicate IDs and payments above the balance receive
HTTP 409. A missing bill receives HTTP 404 and explicitly declining confirmation
receives HTTP 400. Apply `schema.sql` to create the payment table. The payment
record and balance update commit in a single PostgreSQL transaction.

## API tests

From the project directory, install the test dependencies and run pytest:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The tests send requests through FastAPI's test client and mock the PostgreSQL
connection. They cover bill retrieval and validation, both usage increments,
missing or invalid operator credentials, an unsupported usage type, and
bill calculation tariff boundaries, and detailed bill authorization,
paging, legacy invoices, and partial and full payments with failure cases.
They can run without a PostgreSQL server or a live LLM.

Verified result: `33 passed`.
