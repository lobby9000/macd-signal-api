# MACD Signal API: contract and numerical testing

[![QA](https://github.com/lobby9000/macd-signal-api/actions/workflows/ci.yml/badge.svg)](https://github.com/lobby9000/macd-signal-api/actions/workflows/ci.yml)

A REST API over the indicator engine of my MACD Signal Toolkit (EMA, SMA, MACD,
signal line, histogram, crossovers and RSI), with the testing that an API like
this needs: numbers checked against independent references, a contract checked
from the outside with Postman, and regression tests for the defects real market
data exposed in the toolkit.

**Try it in your browser:** the [`api bug` demo](https://lobby9000.github.io/professional.html?app=terminal&run=api%20bug) on my site replays BUG-M01 with the same arithmetic as the engine: three false crossovers on rc1, at periods 45, 50 and 55, and none after the fix. `api` returns a full `POST /v1/macd` response.

## Results

| | |
|---|---|
| Test cases | 25 (11 numerical, 10 contract, 4 regression) |
| pytest, first build (rc1) | 25 of 27 passed: 1 product defect, 1 test-script defect |
| pytest, 1.0.0 | 28 of 28 |
| Postman/Newman, 1.0.0 | 17 requests, 59 of 59 assertions |
| Defects | [BUG-M01](bugs/BUG-M01.md): false crossover events on rounding noise, fixed and verified |

## What is tested and against what

| Area | Reference used as the oracle |
|---|---|
| EMA with both seeds, SMA variant | pandas `ewm(adjust=False)` and `rolling().mean()`, to 1e-10 |
| Signal line start (t = 34 for 12/26/9) | SMA of the first nine MACD values |
| MACD on a straight trend | Closed form: (slow - fast) / 2 x slope = 7 x slope |
| MACD(3,6,3) on a 12-price series | Hand calculation from the course guide |
| RSI | Class example (RS 3.6 gives 78.26), steady rise 100, fall 0, flat 50 |
| Weekly closes | Friday holiday closes on Thursday, partial weeks dropped by `asof` |
| Contract | Minimum sample (33 rejected, 34 accepted), duplicate and unsorted dates, invalid closes, error envelope |

## The defect

On a perfectly straight decline the histogram is mathematically zero, but its
computed values are about 1e-15 with random sign, and the crossover detector
reported three buy and sell signals that do not exist. The same happens with
an illiquid stock that repeats its close. The fix treats values within 1e-9 of
the price scale as zero. The first fix went too far and hid the real cross at
the turn, which the same test caught on retest. Details in [BUG-M01](bugs/BUG-M01.md).

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | Status and version |
| `POST /v1/macd` | MACD, signal, histogram, events and a reading of the last period |
| `POST /v1/rsi` | RSI (Wilder or simple) |

Both POST endpoints accept `prices` (date and close), `freq` (`D`, `W`, `M`) and
`asof`. Interactive docs at `http://localhost:8000/docs`.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                 # 28 tests
uvicorn api.main:app --reload          # http://localhost:8000/docs
scripts/run_newman.sh local            # needs: npm i -g newman newman-reporter-htmlextra
```

`data/sample_prices.csv` is a synthetic random walk so everything runs without
network access. Replace it with a real export (columns `date`, `close`) to
analyse a real ticker.

## Repository map

```
engine/     indicator core from macd_toolkit.py, with the as-of fix and BUG-M01 fix
api/        FastAPI service
docs/       requirements and test cases with results per build
tests/      numerical, contract and regression tests
postman/    collection builder and exported collection
bugs/       defect report
reports/    JUnit and Newman HTML reports for rc1 and 1.0.0
```

Built with AI assistance (Claude). The defect above was found by the test suite,
not planted.

Luis A. Quiroz

Licence: [MIT](LICENSE)

---

Part of the portfolio of Luis Ángel Quiroz López · [lobby9000.github.io](https://lobby9000.github.io) · [LinkedIn](https://www.linkedin.com/in/llqq) · [GitHub](https://github.com/lobby9000)
