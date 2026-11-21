BEGIN;

INSERT INTO monthly_usage (subscriber_no, month, year, phone_minutes, internet_mb)
VALUES ('1001', 1, 2027, 1350, 35000), ('1001', 12, 2026, 0, 0)
ON CONFLICT (subscriber_no, month, year) DO NOTHING;

INSERT INTO bills (
    subscriber_no, month, year, total_amount, paid_amount,
    billed_phone_minutes, billed_internet_mb
)
VALUES ('1001', 1, 2027, 80, 0, 1350, 35000),
       ('1001', 12, 2026, 50, 0, 0, 0)
ON CONFLICT (subscriber_no, month, year) DO NOTHING;

COMMIT;
