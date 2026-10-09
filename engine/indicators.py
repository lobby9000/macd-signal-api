"""
Indicator core of the MACD Signal Toolkit (macd_toolkit.py), packaged for the API.

Same conventions as the toolkit and its Excel twin:

* SMA_N   arithmetic mean of the last N closes, exists from t = N.
* EMA_N   EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}, alpha = 2 / (N + 1).
          Default seed: EMA_N at t = N is the SMA of the first N closes.
          seed="first" starts at EMA_1 = P_1 (pandas ewm(adjust=False)).
* MACD    EMA_fast - EMA_slow                  (exists from t = slow)
* Signal  EMA_signal of the MACD series        (exists from t = slow + signal - 1)
* Hist    MACD - Signal

Changes from the original module, both from defects found with real data:
* resample_close takes `asof` and drops a week or month that is still open on
  that date, so a partial period is never counted as a close (R-01).
* describe_last reads columns by key; `row.hist` returned the pandas method
  Series.hist instead of the value (R-02).
* crossovers ignores rounding noise around zero (BUG-M01).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Kind = Literal["ema", "sma"]
Seed = Literal["sma", "first"]


def alpha_from_span(n: int) -> float:
    if n < 1:
        raise ValueError("N must be >= 1")
    return 2.0 / (n + 1.0)


def sma(x: pd.Series, n: int) -> pd.Series:
    if n < 1:
        raise ValueError("N must be >= 1")
    return x.rolling(window=n, min_periods=n).mean()


def ema(x: pd.Series, n: int, seed: Seed = "sma", alpha: float | None = None) -> pd.Series:
    """EMA by explicit recursion. Leading NaNs are skipped; NaNs after the first value are an error."""
    a = alpha_from_span(n) if alpha is None else float(alpha)
    if not 0.0 < a <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    out = pd.Series(np.nan, index=x.index, dtype="float64")
    valid = x.dropna()
    if valid.index.size and x.loc[valid.index[0]:].isna().any():
        raise ValueError("series has gaps (NaN) after its first value")
    values = valid.to_numpy(dtype="float64")
    if seed == "sma":
        if values.size < n:
            return out
        start, prev = n - 1, values[:n].mean()
    elif seed == "first":
        if values.size == 0:
            return out
        start, prev = 0, values[0]
    else:
        raise ValueError("seed must be 'sma' or 'first'")
    res = np.full(values.size, np.nan)
    res[start] = prev
    for i in range(start + 1, values.size):
        prev = a * values[i] + (1.0 - a) * prev
        res[i] = prev
    out.loc[valid.index] = res
    return out


def moving_average(x: pd.Series, n: int, kind: Kind = "ema", seed: Seed = "sma") -> pd.Series:
    if kind == "sma":
        return sma(x, n)
    if kind == "ema":
        return ema(x, n, seed=seed)
    raise ValueError("kind must be 'ema' or 'sma'")


@dataclass(frozen=True)
class MACDConfig:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    kind: Kind = "ema"
    seed: Seed = "sma"

    def __post_init__(self) -> None:
        if not self.fast < self.slow:
            raise ValueError("fast must be smaller than slow")

    @property
    def first_signal(self) -> int:
        """Closes needed for the first signal value (34 for 12/26/9 with SMA seed)."""
        if self.kind == "sma" or self.seed == "sma":
            return self.slow + self.signal - 1
        return 1


def macd(close: pd.Series, cfg: MACDConfig = MACDConfig()) -> pd.DataFrame:
    close = close.astype("float64")
    ma_fast = moving_average(close, cfg.fast, cfg.kind, cfg.seed)
    ma_slow = moving_average(close, cfg.slow, cfg.kind, cfg.seed)
    line = ma_fast - ma_slow
    signal = moving_average(line, cfg.signal, cfg.kind, cfg.seed)
    return pd.DataFrame({"close": close, "ma_fast": ma_fast, "ma_slow": ma_slow,
                         "macd": line, "signal": signal, "hist": line - signal})


def crossovers(df: pd.DataFrame, rel_tol: float = 1e-9) -> pd.DataFrame:
    """
    bullish_cross: histogram goes from <= 0 to > 0; bearish_cross: from >= 0 to < 0.
    zero_up / zero_down: the same for the MACD line against zero.

    Values within rel_tol x the largest close count as exactly zero. Without this,
    rounding noise around zero (about 1e-15) produced false events (BUG-M01).
    """
    tol = rel_tol * max(1.0, float(np.nanmax(np.abs(df["close"].to_numpy()))))

    def crossings(x: pd.Series):
        sign = pd.Series(np.where(x > tol, 1.0, np.where(x < -tol, -1.0, 0.0)), index=x.index)
        sign[x.isna()] = np.nan
        prev = sign.shift(1)
        ok = sign.notna() & prev.notna()
        return ok & (prev <= 0) & (sign > 0), ok & (prev >= 0) & (sign < 0)

    bull, bear = crossings(df["hist"])
    up, down = crossings(df["macd"])
    events = []
    for mask, label in ((bull, "bullish_cross"), (bear, "bearish_cross"), (up, "zero_up"), (down, "zero_down")):
        for ts in df.index[mask]:
            events.append({"date": ts, "event": label})
    out = pd.DataFrame(events, columns=["date", "event"])
    return out.sort_values(["date", "event"]).reset_index(drop=True)


def describe_last(df: pd.DataFrame) -> str | None:
    valid = df.dropna(subset=["hist"])
    if len(valid) < 2:
        return None
    last, prev = valid.iloc[-1], valid.iloc[-2]
    m, s, h, h0 = last["macd"], last["signal"], last["hist"], prev["hist"]
    side = "above" if m > 0 else "below"
    rel = "above" if h > 0 else "below"
    trend = "widening" if abs(h) > abs(h0) else "narrowing"
    return (f"MACD {m:.4f} is {side} zero and {rel} its signal ({s:.4f}). "
            f"The histogram ({h:.4f}) is {trend} versus the previous period ({h0:.4f}).")


def rsi_from_rs(rs: float) -> float:
    return 100.0 - 100.0 / (1.0 + rs)


def rsi(close: pd.Series, n: int = 14, method: Literal["simple", "wilder"] = "wilder") -> pd.Series:
    delta = close.astype("float64").diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    if method == "simple":
        avg_g = gain.rolling(n, min_periods=n).mean()
        avg_l = loss.rolling(n, min_periods=n).mean()
    elif method == "wilder":
        avg_g = ema(gain, n, seed="sma", alpha=1.0 / n)
        avg_l = ema(loss, n, seed="sma", alpha=1.0 / n)
    else:
        raise ValueError("method must be 'simple' or 'wilder'")
    total = avg_g + avg_l
    out = 100.0 * avg_g / total
    return out.where(total != 0, 50.0)


def resample_close(close: pd.Series, freq: Literal["D", "W", "M"], asof=None) -> pd.Series:
    """
    D: unchanged. W: last close of each week ending Friday (a Friday holiday uses
    the last trading day of that week). M: last close of each month.

    `asof` cuts the data at that date and drops the last week or month when it is
    still open on that date (its Friday or month end is later than `asof`).
    """
    close = close.dropna().sort_index()
    if asof is not None:
        asof = pd.Timestamp(asof)
        close = close[close.index <= asof]
    if freq == "D" or close.empty:
        return close
    if freq == "W":
        rule = "W-FRI"
    elif freq == "M":
        rule = "ME" if int(pd.__version__.split(".")[0]) >= 2 else "M"
    else:
        raise ValueError("freq must be D, W or M")
    values = close.resample(rule).last()
    last_date = close.index.to_series().resample(rule).last()
    out = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(last_date.to_numpy()), name=close.name).dropna()
    if asof is not None and len(values) and values.index[-1] > asof and len(out):
        out = out.iloc[:-1]
    return out
