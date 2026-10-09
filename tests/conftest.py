from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def payload(closes, start="2026-01-05", freq="B", **params) -> dict:
    """Build a request body from a list of closes on consecutive business days."""
    dates = pd.date_range(start, periods=len(closes), freq=freq)
    return {"prices": [{"date": d.date().isoformat(), "close": float(c)} for d, c in zip(dates, closes)], **params}


def random_walk(n=120, seed=7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, n)))


def error_code(r) -> str:
    return r.json()["error"]["code"]
