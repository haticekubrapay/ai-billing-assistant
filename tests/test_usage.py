from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
USAGE_URL = "/api/v1/usage"
USAGE = {"subscriber_no": "1001", "month": 10, "year": 2026, "usage_type": "Phone"}
AUTH = {"Authorization": "Bearer test-operator"}


# Test açıklaması: Telefon isteğinde 10 dakika, internet isteğinde 1 MB eklemek için doğru değerlerin SQL'e gönderildiğini kontrol eder.
@pytest.mark.parametrize(
    "usage_type,phone_minutes,internet_mb", [("Phone", 10, 0), ("Internet", 0, 1)]
)
def test_add_usage_records_increment(monkeypatch, usage_type, phone_minutes, internet_mb):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("usage_router.psycopg.connect") as connect:
        connection = connect.return_value.__enter__.return_value
        response = client.post(USAGE_URL, json={**USAGE, "usage_type": usage_type}, headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    connection.execute.assert_called_once()
    assert connection.execute.call_args.args[1] == ("1001", 10, 2026, phone_minutes, internet_mb)


# Test açıklaması: Token eksik veya yanlışsa kullanım kaydı yapılmadan 401 döndüğünü kontrol eder.
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}])
def test_add_usage_rejects_unauthorized_requests(monkeypatch, headers):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("usage_router.psycopg.connect") as connect:
        response = client.post(USAGE_URL, json=USAGE, headers=headers)

    assert response.status_code == 401
    connect.assert_not_called()


# Test açıklaması: SMS gibi desteklenmeyen bir kullanım türünde 422 döndüğünü kontrol eder.
def test_add_usage_rejects_unsupported_usage_type(monkeypatch):
    monkeypatch.setenv("USAGE_OPERATOR_TOKEN", "test-operator")
    with patch("usage_router.psycopg.connect") as connect:
        response = client.post(USAGE_URL, json={**USAGE, "usage_type": "SMS"}, headers=AUTH)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "usage_type"]
    connect.assert_not_called()
