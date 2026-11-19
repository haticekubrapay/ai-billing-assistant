from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
URL = "/api/v1/bills/1001/details"
PERIOD = {"month": 10, "year": 2026}
AUTH = {"Authorization": "Bearer test-operator"}


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("bill_repository.psycopg.connect") as connect:
        yield connect.return_value.__enter__.return_value


# Test açıklaması: Fatura özetinin, faturaya yansıyan kullanımın ve ücret dökümünün ikinci sayfasının doğru döndüğünü kontrol eder.
def test_returns_usage_and_paged_charges(database):
    database.execute.return_value.fetchone.return_value = (
        Decimal("70"), Decimal("25"), 1010, 20001
    )
    response = client.get(URL, params={**PERIOD, "page": 2, "page_size": 2}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "subscriber_no": "1001",
        "month": 10,
        "year": 2026,
        "total_amount": 70,
        "paid_amount": 25,
        "remaining_balance": 45,
        "status": "partially_paid",
        "phone_minutes": 1010,
        "internet_mb": 20001,
        "internet_gb": 20.001,
        "charges": [{"type": "internet_overage", "amount": 10}],
        "page": 2,
        "page_size": 2,
        "total_items": 3,
    }
    assert database.execute.call_args.args[1] == ("1001", 10, 2026)


# Test açıklaması: Kullanım bilgisi kaydedilmemiş eski faturada toplamın tek bir unitemized kalemi olarak döndüğünü kontrol eder.
def test_returns_unitemized_charge_for_legacy_bill(database):
    database.execute.return_value.fetchone.return_value = (75, 25, None, None)

    response = client.get(URL, params=PERIOD, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["phone_minutes"] is None
    assert response.json()["internet_mb"] is None
    assert response.json()["charges"] == [{"type": "unitemized", "amount": 75}]


# Test açıklaması: Operatör token'ı yoksa fatura detayları okunmadan 401 döndüğünü kontrol eder.
def test_requires_operator_token(database):
    assert client.get(URL, params=PERIOD).status_code == 401
    database.execute.assert_not_called()


# Test açıklaması: Sayfa boyutu üst sınırı aşıldığında 422 döndüğünü kontrol eder.
def test_rejects_invalid_page_size(database):
    response = client.get(URL, params={**PERIOD, "page_size": 101}, headers=AUTH)

    assert response.status_code == 422
    database.execute.assert_not_called()


# Test açıklaması: Detayı istenen fatura bulunamazsa 404 döndüğünü kontrol eder.
def test_returns_404_for_missing_bill(database):
    database.execute.return_value.fetchone.return_value = None

    response = client.get(URL, params=PERIOD, headers=AUTH)

    assert response.status_code == 404
    assert response.json() == {"detail": "Bill not found."}
