# Requirements: MACD Signal API 1.0

The API exposes the indicator engine of the MACD Signal Toolkit over HTTP so
other tools (a dashboard, a spreadsheet macro, a notebook) can request MACD and
RSI without installing Python. Formulas and conventions are the toolkit's,
already cross-validated against an Excel workbook to within 5e-13.

## Calculation

| ID | Requirement |
|---|---|
| REQ-NUM-01 | EMA uses alpha = 2/(N+1). With `seed=sma` the first value, at t = N, is the SMA of the first N closes. With `seed=first` it is the first close (same as pandas `ewm(adjust=False)`). |
| REQ-NUM-02 | MACD = MA(fast) - MA(slow). Signal = MA(signal) of the MACD series, starting at its first valid value. Histogram = MACD - Signal. `kind=sma` uses simple averages for all three. |
| REQ-NUM-03 | With SMA seeding the first signal value appears at t = slow + signal - 1 (34 for 12/26/9). Earlier values are `null`. |
| REQ-NUM-04 | Events: `bullish_cross` when the histogram goes from <= 0 to > 0, `bearish_cross` from >= 0 to < 0, `zero_up` and `zero_down` when the MACD crosses zero. Values within 1e-9 times the largest close count as exactly zero (BUG-M01). |
| REQ-NUM-05 | RSI uses Wilder smoothing by default (first average arithmetic, then alpha = 1/N) or a simple rolling mean with `method=simple`. With no movement at all the RSI is 50. |

## Resampling

| ID | Requirement |
|---|---|
| REQ-RSM-01 | `freq=W` keeps the last close of each week ending Friday. If the Friday is a holiday, the week closes on its last trading day. `freq=M` keeps the last close of each month. |
| REQ-RSM-02 | `asof` cuts the data at that date. A week or month that is still open on `asof` (its Friday or month end is later) is dropped, so a partial period is never reported as a close. |
| REQ-RSM-03 | When `asof` is omitted it defaults to the date of the last price. Known limitation: a week whose Friday is a holiday counts as complete only once `asof` is that Friday or later. |

## API contract

| ID | Requirement |
|---|---|
| REQ-API-01 | `POST /v1/macd` and `POST /v1/rsi` take `prices` (1 to 20,000 points of `date` and `close`) plus their parameters. `GET /health` returns status and version. |
| REQ-API-02 | Errors use `{"error": {"code", "message", "details"}}`. Schema errors return 422 `VALIDATION_ERROR` (missing or unknown fields, close <= 0, parameters out of range). |
| REQ-API-03 | `fast >= slow` returns 422 `INVALID_CONFIG`. Repeated dates return 422 `DUPLICATE_DATE`. Dates out of order return 422 `UNSORTED_DATES`. An `asof` before the first price returns 422 `INVALID_ASOF`. |
| REQ-API-04 | Fewer periods than the signal needs (after resampling) returns 422 `INSUFFICIENT_DATA` with `required` and `available` in the details. Exactly the required number returns 200 with one signal value. |
| REQ-API-05 | The response includes the configuration, the effective `asof`, the full series, the events and a plain-language reading of the last period. |

## Regression requirements from the toolkit's history

| ID | Defect found with real data | Requirement |
|---|---|---|
| R-01 | The weekly resampler counted the current, unfinished week as a close, which changed a buy/sell reading | REQ-RSM-02 |
| R-02 | The last-period reading crashed because `row.hist` returned the pandas method `Series.hist` instead of the column value | REQ-API-05 |
