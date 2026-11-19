from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
URL = "/api/v1/bills/calculate"
PERIOD = {"subscriber_no": "1001", "month": 11, "year": 2026}
AUTH = {"Authorization": "Bearer test-operator"}


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("bill_repository.psycopg.connect") as connect:
        yield connect.return_value.__enter__.return_value


# Test açıklaması: Beş örnekte telefon ve internet aşım eşiklerine göre doğru fatura tutarının hesaplandığını kontrol eder.
@pytest.mark.parametrize(
    "usage,total",
    [((1000, 20000), 50), ((1001, 20000), 60), ((1000, 20001), 60),
     ((2000, 30000), 70), ((2001, 30001), 90)],
)
def test_calculate_bill_applies_tariff(database, usage, total):
    database.execute.return_value.fetchone.side_effect = [usage, (total,)]

    response = client.post(URL, json=PERIOD, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    assert database.execute.call_args.args[1] == ("1001", 11, 2026, total, *usage)


# Test açıklaması: Seçilen dönemde kullanım kaydı yoksa 404 döndüğünü kontrol eder.
def test_calculate_bill_requires_usage(database):
    database.execute.return_value.fetchone.return_value = None

    response = client.post(URL, json=PERIOD, headers=AUTH)

    assert response.status_code == 404
    assert response.json() == {"detail": "Usage not found."}
    database.execute.assert_called_once()


# Test açıklaması: Hesaplanan toplam ödenmiş tutarın altına düşerse 409 döndüğünü kontrol eder.
def test_calculate_bill_rejects_total_below_payment(database):
    database.execute.return_value.fetchone.side_effect = [(1000, 20000), None]

    response = client.post(URL, json=PERIOD, headers=AUTH)

    assert response.status_code == 409


# Test açıklaması: Operatör token'ı yoksa fatura hesaplanmadan 401 döndüğünü kontrol eder.
def test_calculate_bill_requires_operator_token(database):
    response = client.post(URL, json=PERIOD)

    assert response.status_code == 401
    database.execute.assert_not_called()


# Test açıklaması: Ay 13 girildiğinde fatura hesaplanmadan 422 döndüğünü kontrol eder.
def test_calculate_bill_rejects_invalid_month(database):
    response = client.post(URL, json={**PERIOD, "month": 13}, headers=AUTH)

    assert response.status_code == 422
    database.execute.assert_not_called()
