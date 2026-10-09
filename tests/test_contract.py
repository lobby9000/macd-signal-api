"""API contract: validation, boundaries, resampling and error envelope."""

import pytest

from conftest import error_code, payload, random_walk


def test_TC_API_001_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_TC_API_002_daily_happy_path(client):
    r = client.post("/v1/macd", json=payload(random_walk(60)))
    assert r.status_code == 200
    body = r.json()
    assert body["periods"] == 60 and body["first_signal_period"] == 34
    assert body["config"] == {"fast": 12, "slow": 26, "signal": 9, "kind": "ema", "seed": "sma"}
    assert body["last"]["reading"]


def test_TC_API_003_weekly_friday_holiday_uses_thursday(client):
    closes = random_walk(15)
    body = payload(closes, start="2026-08-31")  # Mon 2026-08-31 .. Fri 2026-09-18
    body["prices"] = [p for p in body["prices"] if p["date"] != "2026-09-11"]  # Friday holiday
    r = client.post("/v1/rsi", json={**body, "freq": "W", "n": 1})
    assert [p["date"] for p in r.json()["series"]] == ["2026-09-04", "2026-09-10", "2026-09-18"]


def test_TC_API_004_fast_must_be_below_slow(client):
    r = client.post("/v1/macd", json=payload(random_walk(60), fast=26, slow=26))
    assert r.status_code == 422 and error_code(r) == "INVALID_CONFIG"


@pytest.mark.parametrize("n,status", [(33, 422), (34, 200)])
def test_TC_API_005_minimum_sample_boundary(client, n, status):
    r = client.post("/v1/macd", json=payload(random_walk(n)))
    assert r.status_code == status
    if status == 422:
        assert error_code(r) == "INSUFFICIENT_DATA"
        assert r.json()["error"]["details"] == [{"required": 34, "available": 33}]
    else:
        signals = [p["signal"] for p in r.json()["series"] if p["signal"] is not None]
        assert len(signals) == 1


@pytest.mark.parametrize("close", [0, -1.5, "abc"])
def test_TC_API_006_invalid_close(client, close):
    body = payload(random_walk(40))
    body["prices"][5]["close"] = close
    r = client.post("/v1/macd", json=body)
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_TC_API_007_duplicate_and_unsorted_dates(client):
    body = payload(random_walk(40))
    body["prices"][7]["date"] = body["prices"][6]["date"]
    r = client.post("/v1/macd", json=body)
    assert r.status_code == 422 and error_code(r) == "DUPLICATE_DATE"
    body = payload(random_walk(40))
    body["prices"][6], body["prices"][7] = body["prices"][7], body["prices"][6]
    r = client.post("/v1/macd", json=body)
    assert r.status_code == 422 and error_code(r) == "UNSORTED_DATES"


def test_TC_API_008_schema_errors(client):
    r = client.post("/v1/macd", json={"freq": "W"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
    r = client.post("/v1/macd", json={**payload(random_walk(40)), "window": 5})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
    r = client.post("/v1/macd", json={**payload(random_walk(40)), "freq": "H"})
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"


def test_TC_API_009_asof_before_first_price(client):
    r = client.post("/v1/macd", json=payload(random_walk(40), asof="2025-12-31"))
    assert r.status_code == 422 and error_code(r) == "INVALID_ASOF"


def test_TC_API_010_error_envelope_for_framework_errors(client):
    r = client.get("/nope")
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"
    r = client.get("/v1/macd")
    assert r.status_code == 405 and error_code(r) == "METHOD_NOT_ALLOWED"
