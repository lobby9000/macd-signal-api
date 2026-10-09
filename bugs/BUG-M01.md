# BUG-M01 Crossover events are reported on floating-point noise

| Field | Value |
|---|---|
| Severity | S2 Major |
| Priority | High |
| Status | Closed (verified) |
| Affects version | 1.0.0-rc1, and `crossovers()` in macd_toolkit.py |
| Fix version | 1.0.0 |
| Component | Engine, events |
| Requirement | REQ-NUM-04 |
| Found by | TC-NUM-010 |
| Reported by | Luis A. Quiroz |

## Steps to reproduce

1. `POST /v1/macd` with 60 closes falling in a straight line from 100 to 80, followed by 60 closes rising to 110 (default 12/26/9).
2. Read `events`.

## Expected result

No crossover while the price falls in a straight line. The first `bullish_cross` comes after the turn at period 60.

## Actual result

Three events during the straight decline: `bullish_cross` at period 45, `bearish_cross` at 50 and `bullish_cross` at 55. In that stretch the histogram is mathematically zero and its computed values are of order 1e-15 with random sign.

## Impact

Any flat or perfectly steady stretch can produce false buy and sell signals. Real prices are rarely perfectly linear, but an illiquid stock that repeats the same close for several sessions gives a MACD of zero and the same noise. The toolkit's `crossovers()` has the same behaviour, so the CLI reports would show it too.

## Root cause

The detector compared the raw histogram with zero (`h_prev <= 0 and h > 0`), so the sign of rounding noise decided the event.

Fix: values within 1e-9 times the largest close are treated as exactly zero before applying the same rule. A first attempt that also required a sign change between two non-zero values was rejected by TC-NUM-010 itself: it hid the genuine cross at the turn, where the histogram leaves zero for the first time.

## Verification

TC-NUM-010 passes (first `bullish_cross` after the turn). TC-NUM-011 added: 40 identical closes produce no events.

## History

| Date | Build | Event |
|---|---|---|
| 2026-10-08 | 1.0.0-rc1 | Opened |
| 2026-10-08 | 1.0.0 | Fixed and verified |
