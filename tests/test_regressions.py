"""Regression tests for the two defects the toolkit hit with real data (R-01, R-02)."""

from conftest import payload, random_walk


def weekly_body(asof=None, last_day="2026-09-16"):
    """Business days from Mon 2026-01-05 to `last_day` (a Wednesday by default)."""
    import pandas as pd

    days = pd.bdate_range("2026-01-05", last_day)
    closes = random_walk(len(days))
    body = {"prices": [{"date": d.date().isoformat(), "close": float(c)} for d, c in zip(days, closes)],
            "freq": "W"}
    if asof:
        body["asof"] = asof
    return body


def test_TC_REG_001_partial_week_is_not_a_close(client):
    # R-01: data runs to Wednesday 2026-09-16; that week ends Friday 2026-09-18
    r = client.post("/v1/macd", json=weekly_body(asof="2026-09-16")).json()
    assert r["series"][-1]["date"] == "2026-09-11"


def test_TC_REG_002_default_asof_is_the_last_price(client):
    r = client.post("/v1/macd", json=weekly_body()).json()
    assert r["asof"] == "2026-09-16"
    assert r["series"][-1]["date"] == "2026-09-11"


def test_TC_REG_003_complete_week_is_kept(client):
    r = client.post("/v1/macd", json=weekly_body(last_day="2026-09-18")).json()
    assert r["series"][-1]["date"] == "2026-09-18"


def test_TC_REG_004_last_period_reading_works(client):
    # R-02: the reading used row.hist, which is the pandas method, not the value
    r = client.post("/v1/macd", json=payload(random_walk(80))).json()
    reading = r["last"]["reading"]
    assert reading.startswith("MACD ") and "histogram" in reading
