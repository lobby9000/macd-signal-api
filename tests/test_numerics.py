"""Numerical checks against independent references (pandas and hand calculation)."""

import numpy as np
import pandas as pd
import pytest

from conftest import payload, random_walk
from engine import indicators as ind


def values(r, field):
    return np.array([p[field] if p[field] is not None else np.nan for p in r.json()["series"]], dtype=float)


def test_TC_NUM_001_ema_first_seed_equals_pandas(client):
    x = random_walk()
    r = client.post("/v1/macd", json=payload(x, seed="first"))
    expected = pd.Series(x).ewm(span=12, adjust=False).mean().to_numpy()
    assert np.allclose(values(r, "ma_fast"), expected, rtol=0, atol=1e-10)


def test_TC_NUM_002_ema_sma_seed_equals_pandas_after_seed(client):
    x = random_walk()
    r = client.post("/v1/macd", json=payload(x))
    n = 26
    seeded = pd.Series(np.r_[x[:n].mean(), x[n:]]).ewm(span=n, adjust=False).mean().to_numpy()
    got = values(r, "ma_slow")
    assert np.isnan(got[: n - 1]).all()
    assert np.allclose(got[n - 1:], seeded, rtol=0, atol=1e-10)


def test_TC_NUM_003_sma_kind_equals_rolling_means(client):
    x = random_walk()
    r = client.post("/v1/macd", json=payload(x, kind="sma"))
    s = pd.Series(x)
    macd = (s.rolling(12).mean() - s.rolling(26).mean()).to_numpy()
    assert np.allclose(values(r, "macd"), macd, equal_nan=True, atol=1e-10)


def test_TC_NUM_004_linear_trend_macd_tends_to_7_times_slope(client):
    slope = 0.5
    x = 100 + slope * np.arange(200)
    r = client.post("/v1/macd", json=payload(x))
    # (slow - fast) / 2 * slope = 7 * slope for 12/26, and the histogram goes to zero
    assert values(r, "macd")[-1] == pytest.approx(7 * slope, abs=1e-6)
    assert values(r, "hist")[-1] == pytest.approx(0, abs=1e-6)


def test_TC_NUM_005_signal_starts_at_t34_with_sma_seed(client):
    r = client.post("/v1/macd", json=payload(random_walk()))
    sig = values(r, "signal")
    assert np.isnan(sig[:33]).all() and not np.isnan(sig[33])
    macd = values(r, "macd")
    assert sig[33] == pytest.approx(np.mean(macd[25:34]), abs=1e-12)  # SMA of the first nine MACD values


def test_TC_NUM_006_histogram_is_macd_minus_signal(client):
    r = client.post("/v1/macd", json=payload(random_walk()))
    assert np.allclose(values(r, "hist"), values(r, "macd") - values(r, "signal"), equal_nan=True, atol=0)


def test_TC_NUM_007_seed_difference_decays_by_one_minus_alpha(client):
    x = random_walk()
    a = values(client.post("/v1/macd", json=payload(x, seed="sma")), "ma_fast")
    b = values(client.post("/v1/macd", json=payload(x, seed="first")), "ma_fast")
    d = a[11:] - b[11:]
    d = d[np.abs(d) > 1e-6]  # below this the difference is dominated by float rounding
    ratio = d[1:] / d[:-1]
    assert len(ratio) > 30
    assert np.allclose(ratio, 1 - 2 / 13, atol=1e-7)


def test_TC_NUM_008_hand_example_macd_3_6_3(client):
    x = [10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 14, 15]
    r = client.post("/v1/macd", json=payload(x, fast=3, slow=6, signal=3))

    def hand_ema(seq, n):  # seed = SMA of the first n values, then the recursion by hand
        a, out = 2 / (n + 1), [None] * (n - 1)
        prev = sum(seq[:n]) / n
        out.append(prev)
        for v in seq[n:]:
            prev = a * v + (1 - a) * prev
            out.append(prev)
        return out

    e3, e6 = hand_ema(x, 3), hand_ema(x, 6)
    macd = [e3[i] - e6[i] for i in range(5, len(x))]
    signal = hand_ema(macd, 3)
    got_macd, got_sig = values(r, "macd"), values(r, "signal")
    assert np.allclose(got_macd[5:], macd, atol=1e-12)
    assert np.allclose(got_sig[7:], [s for s in signal if s is not None], atol=1e-12)


def test_TC_NUM_009_rsi_reference_values(client):
    assert ind.rsi_from_rs(3.6) == pytest.approx(78.26, abs=0.005)  # class example
    up = client.post("/v1/rsi", json=payload(list(range(1, 31)))).json()["series"]
    down = client.post("/v1/rsi", json=payload(list(range(30, 0, -1)))).json()["series"]
    flat = client.post("/v1/rsi", json=payload([5.0] * 30)).json()["series"]
    assert up[-1]["rsi"] == 100.0 and down[-1]["rsi"] == 0.0 and flat[-1]["rsi"] == 50.0
    assert up[13]["rsi"] is None and up[14]["rsi"] is not None  # first value after 14 changes


def test_TC_NUM_010_events_on_a_known_crossing(client):
    x = np.r_[np.linspace(100, 80, 60), np.linspace(80, 110, 60)]  # down then up
    r = client.post("/v1/macd", json=payload(x)).json()
    kinds = [e["event"] for e in r["events"]]
    assert "bullish_cross" in kinds and "zero_up" in kinds
    first_bull = next(e for e in r["events"] if e["event"] == "bullish_cross")
    assert first_bull["date"] > r["series"][59]["date"]  # after the turn, never before


def test_TC_NUM_011_flat_prices_produce_no_events(client):
    r = client.post("/v1/macd", json=payload([25.40] * 40)).json()
    assert r["events"] == []
