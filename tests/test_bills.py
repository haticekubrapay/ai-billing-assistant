from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
BILL_URL = "/api/v1/bills/1001"


# Test açıklaması: Kısmi ödenmiş faturada 200 yanıtını, fatura alanlarını ve kalan bakiyenin 50 olduğunu kontrol eder.
def test_query_bill_returns_remaining_balance():
    with patch("bill_repository.psycopg.connect") as connect:
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = (
            Decimal("75.00"),
            Decimal("25.00"),
        )

        response = client.get(BILL_URL, params={"month": 10, "year": 2026})

    assert response.status_code == 200
    assert response.json() == {
        "subscriber_no": "1001",
        "month": 10,
        "year": 2026,
        "total_amount": 75,
        "paid_amount": 25,
        "remaining_balance": 50,
        "status": "partially_paid",
    }
    connection.execute.assert_called_once()
    assert connection.execute.call_args.args[1] == ("1001", 10, 2026)


# Test açıklaması: İstenen döneme ait fatura bulunamazsa 404 döndüğünü kontrol eder.
def test_query_bill_returns_404_when_bill_is_missing():
    with patch("bill_repository.psycopg.connect") as connect:
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = None

        response = client.get(BILL_URL, params={"month": 8, "year": 2026})

    assert response.status_code == 404
    assert response.json() == {"detail": "Bill not found."}


# Test açıklaması: Ay 13 girildiğinde veritabanına erişilmeden 422 döndüğünü kontrol eder.
def test_query_bill_rejects_invalid_month_before_database_lookup():
    with patch("bill_repository.psycopg.connect") as connect:
        response = client.get(BILL_URL, params={"month": 13, "year": 2026})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "month"]
    connect.assert_not_called()
