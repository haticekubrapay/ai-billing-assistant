CREATE TABLE IF NOT EXISTS bills (
    subscriber_no text NOT NULL,
    month integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    year integer NOT NULL,
    total_amount numeric(12, 2) NOT NULL CHECK (total_amount >= 0),
    paid_amount numeric(12, 2) NOT NULL CHECK (paid_amount BETWEEN 0 AND total_amount),
    PRIMARY KEY (subscriber_no, month, year)
);

ALTER TABLE bills
    ADD COLUMN IF NOT EXISTS billed_phone_minutes bigint CHECK (billed_phone_minutes >= 0),
    ADD COLUMN IF NOT EXISTS billed_internet_mb bigint CHECK (billed_internet_mb >= 0);

INSERT INTO bills (subscriber_no, month, year, total_amount, paid_amount)
VALUES ('1001', 10, 2026, 75, 25)
ON CONFLICT (subscriber_no, month, year) DO NOTHING;

CREATE TABLE IF NOT EXISTS monthly_usage (
    subscriber_no text NOT NULL,
    month integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    year integer NOT NULL CHECK (year BETWEEN 1 AND 9999),
    phone_minutes bigint NOT NULL CHECK (phone_minutes >= 0),
    internet_mb bigint NOT NULL CHECK (internet_mb >= 0),
    PRIMARY KEY (subscriber_no, month, year)
);

CREATE TABLE IF NOT EXISTS bill_payments (
    transaction_id text PRIMARY KEY,
    subscriber_no text NOT NULL,
    month integer NOT NULL,
    year integer NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    FOREIGN KEY (subscriber_no, month, year) REFERENCES bills (subscriber_no, month, year)
);
