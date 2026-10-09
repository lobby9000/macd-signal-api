"""Synthetic daily closes for demos and Postman (no network needed).

Geometric random walk on business days, fixed seed. NOT market data: replace
data/sample_prices.csv with a real export (columns date, close) to analyse a
real ticker.
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(11)
idx = pd.bdate_range("2024-09-02", "2026-09-18")
prices = 180 * np.exp(np.cumsum(rng.normal(0.0002, 0.013, len(idx))))
out = Path(__file__).resolve().parent / "sample_prices.csv"
pd.DataFrame({"date": idx.strftime("%Y-%m-%d"), "close": prices.round(2)}).to_csv(out, index=False)
print(f"wrote {out.name}: {len(idx)} business days")
