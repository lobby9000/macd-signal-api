"""MACD Signal API: indicator endpoints over the toolkit's engine."""

from __future__ import annotations

import math
from datetime import date
from typing import List, Literal, Optional

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from engine import indicators as ind

VERSION = "1.0.0"
app = FastAPI(title="MACD Signal API", version=VERSION)


# ---------------------------------------------------------------- errors

class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details or []


def envelope(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=envelope(exc.code, exc.message, exc.details))


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    details = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content=envelope("VALIDATION_ERROR", "Request is not valid", details))


@app.exception_handler(StarletteHTTPException)
async def _http(_: Request, exc: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code, content=envelope(code, str(exc.detail)),
                        headers=getattr(exc, "headers", None))


# ---------------------------------------------------------------- schemas

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PricePoint(Strict):
    date: date
    close: float = Field(gt=0, allow_inf_nan=False)


class Series(Strict):
    prices: List[PricePoint] = Field(min_length=1, max_length=20000)
    freq: Literal["D", "W", "M"] = "D"
    asof: Optional[date] = None


class MacdIn(Series):
    fast: int = Field(12, ge=1, le=500)
    slow: int = Field(26, ge=2, le=500)
    signal: int = Field(9, ge=1, le=500)
    kind: Literal["ema", "sma"] = "ema"
    seed: Literal["sma", "first"] = "sma"


class RsiIn(Series):
    n: int = Field(14, ge=1, le=500)
    method: Literal["wilder", "simple"] = "wilder"


# ---------------------------------------------------------------- helpers

def num(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def to_series(body: Series) -> tuple[pd.Series, pd.Timestamp]:
    dates = [p.date for p in body.prices]
    if len(set(dates)) != len(dates):
        dupes = sorted({d.isoformat() for d in dates if dates.count(d) > 1})
        raise ApiError(422, "DUPLICATE_DATE", "Each date may appear only once", dupes)
    if any(b <= a for a, b in zip(dates, dates[1:])):
        raise ApiError(422, "UNSORTED_DATES", "Prices must be in strictly increasing date order")
    asof = pd.Timestamp(body.asof or dates[-1])
    if asof < pd.Timestamp(dates[0]):
        raise ApiError(422, "INVALID_ASOF", "asof is earlier than the first price")
    s = pd.Series([p.close for p in body.prices], index=pd.DatetimeIndex(pd.to_datetime(dates)), name="close")
    return ind.resample_close(s, body.freq, asof), asof


# ---------------------------------------------------------------- endpoints

@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.post("/v1/macd")
def macd_endpoint(body: MacdIn):
    if body.fast >= body.slow:
        raise ApiError(422, "INVALID_CONFIG", "fast must be smaller than slow")
    cfg = ind.MACDConfig(body.fast, body.slow, body.signal, kind=body.kind, seed=body.seed)
    close, asof = to_series(body)
    if len(close) < cfg.first_signal:
        raise ApiError(422, "INSUFFICIENT_DATA",
                       f"The signal line needs {cfg.first_signal} periods and {len(close)} are available",
                       [{"required": cfg.first_signal, "available": len(close)}])
    df = ind.macd(close, cfg)
    last_valid = df.dropna(subset=["hist"])
    last = last_valid.iloc[-1]
    return {
        "config": {"fast": cfg.fast, "slow": cfg.slow, "signal": cfg.signal, "kind": cfg.kind, "seed": cfg.seed},
        "freq": body.freq,
        "asof": asof.date().isoformat(),
        "periods": len(df),
        "first_signal_period": cfg.first_signal,
        "series": [
            {"date": ts.date().isoformat(), "close": num(r["close"]), "ma_fast": num(r["ma_fast"]),
             "ma_slow": num(r["ma_slow"]), "macd": num(r["macd"]), "signal": num(r["signal"]),
             "hist": num(r["hist"])}
            for ts, r in df.iterrows()
        ],
        "events": [{"date": e["date"].date().isoformat(), "event": e["event"]}
                   for _, e in ind.crossovers(df).iterrows()],
        "last": {"date": last_valid.index[-1].date().isoformat(), "macd": num(last["macd"]),
                 "signal": num(last["signal"]), "hist": num(last["hist"]), "reading": ind.describe_last(df)},
    }


@app.post("/v1/rsi")
def rsi_endpoint(body: RsiIn):
    close, asof = to_series(body)
    if len(close) < body.n + 1:
        raise ApiError(422, "INSUFFICIENT_DATA", f"RSI({body.n}) needs {body.n + 1} periods",
                       [{"required": body.n + 1, "available": len(close)}])
    values = ind.rsi(close, body.n, body.method)
    return {"n": body.n, "method": body.method, "freq": body.freq, "asof": asof.date().isoformat(),
            "series": [{"date": ts.date().isoformat(), "rsi": num(v)} for ts, v in values.items()]}
