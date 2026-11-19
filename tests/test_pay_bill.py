from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
URL = "/api/v1/bills/pay"
PAYMENT = {
    "subscriber_no": "1001",
    "month": 10,
    "year": 2026,
    "amount": "10.25",
    "transaction_id": "pay-001",
    "confirmed": True,
}
AUTH = {"Authorization": "Bearer test-operator"}


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("bill_repository.psycopg.connect") as connect:
        yield connect


# Test açıklaması: Kısmi ve tam ödemede ödeme kaydının, toplam ödenen tutarın ve kalan bakiyenin doğru olduğunu kontrol eder.
@pytest.mark.parametrize("amount,paid,balance", [("10.25", 35.25, 39.75), ("50", 75, 0)])
def test_records_partial_or_full_payment(database, amount, paid, balance):
    connection = database.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.side_effect = [
        (Decimal("75"), Decimal("25")), ("pay-001",)
    ]
    response = client.post(URL, json={**PAYMENT, "amount": amount}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "success", "paid_amount": paid, "remaining_balance": balance}
    assert connection.execute.call_args_list[1].args[1] == (
        "pay-001", "1001", 10, 2026, Decimal(amount)
    )
    assert connection.execute.call_args.args[1] == (Decimal(str(paid)), "1001", 10, 2026)


# Test açıklaması: Tekrarlanan işlem kimliğinde veya bakiye aşımında 409 döndüğünü ve faturanın güncellenmediğini kontrol eder.
@pytest.mark.parametrize(
    "amount,insert_result,detail",
    [
        ("10.25", None, "Transaction ID already exists."),
        ("50.01", ("pay-001",), "Payment exceeds remaining balance."),
    ],
)
def test_rejects_duplicate_or_excess_payment(database, amount, insert_result, detail):
    transaction = database.return_value
    connection = transaction.__enter__.return_value
    connection.execute.return_value.fetchone.side_effect = [
        (Decimal("75"), Decimal("25")), insert_result
    ]
    response = client.post(URL, json={**PAYMENT, "amount": amount}, headers=AUTH)

    assert response.status_code == 409
    assert response.json() == {"detail": detail}
    assert connection.execute.call_count == 2
    assert transaction.__exit__.call_args.args[0] is not None


# Test açıklaması: Ödenecek fatura bulunamazsa 404 döndüğünü kontrol eder.
def test_returns_404_for_missing_bill(database):
    connection = database.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = None

    assert client.post(URL, json=PAYMENT, headers=AUTH).status_code == 404
    connection.execute.assert_called_once()


# Test açıklaması: Eksik yetki, geçersiz onay veya geçersiz tutarda veritabanına erişilmeden hata döndüğünü kontrol eder.
@pytest.mark.parametrize(
    "changes,headers,expected",
    [
        ({}, {}, 401),
        ({"confirmed": False}, AUTH, 400),
        ({"confirmed": "true"}, AUTH, 422),
        ({"amount": "0"}, AUTH, 422),
        ({"amount": "1.001"}, AUTH, 422),
    ],
)
def test_rejects_invalid_requests_before_database_access(database, changes, headers, expected):
    response = client.post(URL, json={**PAYMENT, **changes}, headers=headers)

    assert response.status_code == expected
    database.assert_not_called()
