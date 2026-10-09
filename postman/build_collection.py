"""
Build the Postman collection for the MACD Signal API (v2.1).

Request bodies are generated from data/sample_prices.csv (synthetic) and small
hand-made series, so expected values are known. Request names carry the test
case IDs of docs/test-cases.csv.

Usage: python postman/build_collection.py
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

COLLECTION_TESTS = """
if (pm.response.code >= 400) {
    pm.test("Error body follows the envelope (REQ-API-02)", function () {
        pm.expect(pm.response.json().error).to.have.all.keys("code", "message", "details");
    });
}
pm.test("Response time under 2 s", function () { pm.expect(pm.response.responseTime).to.be.below(2000); });
"""


def sample(until: str | None = None, n: int | None = None) -> list[dict]:
    rows = list(csv.DictReader(open(ROOT / "data" / "sample_prices.csv", encoding="utf-8")))
    if until:
        rows = [r for r in rows if r["date"] <= until]
    if n:
        rows = rows[:n]
    return [{"date": r["date"], "close": float(r["close"])} for r in rows]


def series(closes, start=date(2026, 1, 5)) -> list[dict]:
    out, d = [], start
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"date": d.isoformat(), "close": float(c)})  # exact floats, no rounding
        d += timedelta(days=1)
    return out


def req(name, method, path, body=None, tests=""):
    item = {"name": name,
            "request": {"method": method, "header": [{"key": "Content-Type", "value": "application/json"}],
                        "url": {"raw": "{{baseUrl}}" + path, "host": ["{{baseUrl}}"],
                                "path": [p for p in path.split("/") if p]}},
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": tests.strip().splitlines()}}]}
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body), "options": {"raw": {"language": "json"}}}
    return item


def status(tc, code):
    return f'pm.test("{tc} status {code}", function () {{ pm.response.to.have.status({code}); }});\n'


def error(tc, code, http=422):
    return status(tc, http) + f'pm.test("{tc} code {code}", function () {{ pm.expect(pm.response.json().error.code).to.eql("{code}"); }});\n'


def build() -> dict:
    linear = [100 - 20 * i / 59 for i in range(60)] + [80 + 30 * i / 59 for i in range(60)]
    no_friday = [p for p in series(range(100, 115), start=date(2026, 8, 31)) if p["date"] != "2026-09-11"]
    dup = sample(n=40)
    dup[7] = dict(dup[7], date=dup[6]["date"])
    unsorted = sample(n=40)
    unsorted[6], unsorted[7] = unsorted[7], unsorted[6]
    bad_close = sample(n=40)
    bad_close[5] = dict(bad_close[5], close=0)

    items = [
        req("TC-API-001 Health", "GET", "/health", tests=status("TC-API-001", 200)),
        req("TC-API-002 Daily MACD on 60 periods", "POST", "/v1/macd", {"prices": sample(n=60)},
            status("TC-API-002", 200) + """
pm.test("TC-API-002 shape and first signal at t=34", function () {
    const j = pm.response.json();
    pm.expect(j.periods).to.eql(60);
    pm.expect(j.first_signal_period).to.eql(34);
    pm.expect(j.series[32].signal).to.eql(null);
    pm.expect(j.series[33].signal).to.be.a("number");
    pm.expect(j.last.reading).to.be.a("string").and.not.empty;
});"""),
        req("TC-API-005 33 periods are not enough", "POST", "/v1/macd", {"prices": sample(n=33)},
            error("TC-API-005", "INSUFFICIENT_DATA") + """
pm.test("TC-API-005 required and available", function () {
    pm.expect(pm.response.json().error.details).to.eql([{required: 34, available: 33}]);
});"""),
        req("TC-API-005 34 periods give exactly one signal value", "POST", "/v1/macd", {"prices": sample(n=34)},
            status("TC-API-005", 200) + """
pm.test("TC-API-005 one signal value", function () {
    const n = pm.response.json().series.filter(function (p) { return p.signal !== null; }).length;
    pm.expect(n).to.eql(1);
});"""),
        req("TC-API-004 fast must be below slow", "POST", "/v1/macd", {"prices": sample(n=60), "fast": 26, "slow": 26},
            error("TC-API-004", "INVALID_CONFIG")),
        req("TC-API-006 Close must be positive", "POST", "/v1/macd", {"prices": bad_close},
            error("TC-API-006", "VALIDATION_ERROR")),
        req("TC-API-007 Repeated date", "POST", "/v1/macd", {"prices": dup}, error("TC-API-007", "DUPLICATE_DATE")),
        req("TC-API-007 Dates out of order", "POST", "/v1/macd", {"prices": unsorted},
            error("TC-API-007", "UNSORTED_DATES")),
        req("TC-API-009 asof before the first price", "POST", "/v1/macd",
            {"prices": sample(n=40), "asof": "2024-01-01"}, error("TC-API-009", "INVALID_ASOF")),
        req("TC-NUM-010 Straight decline then rise: first bullish cross after the turn", "POST", "/v1/macd",
            {"prices": series(linear)}, status("TC-NUM-010", 200) + """
pm.test("TC-NUM-010 no false events before the turn", function () {
    const j = pm.response.json();
    const turn = j.series[59].date;
    const bull = j.events.filter(function (e) { return e.event === "bullish_cross"; });
    pm.expect(bull.length).to.be.above(0);
    pm.expect(bull[0].date > turn).to.be.true;
});"""),
        req("TC-NUM-011 Flat prices produce no events", "POST", "/v1/macd", {"prices": series([25.4] * 40)},
            status("TC-NUM-011", 200) + """
pm.test("TC-NUM-011 events empty", function () { pm.expect(pm.response.json().events).to.eql([]); });"""),
        req("TC-REG-001 Partial week is not a close (asof Wednesday)", "POST", "/v1/macd",
            {"prices": sample(until="2026-09-16"), "freq": "W"}, status("TC-REG-001", 200) + """
pm.test("TC-REG-001 last weekly close is the previous Friday", function () {
    const j = pm.response.json();
    pm.expect(j.asof).to.eql("2026-09-16");
    pm.expect(j.series[j.series.length - 1].date).to.eql("2026-09-11");
});"""),
        req("TC-REG-003 Complete week is kept", "POST", "/v1/macd",
            {"prices": sample(until="2026-09-18"), "freq": "W"}, status("TC-REG-003", 200) + """
pm.test("TC-REG-003 last weekly close is Friday 2026-09-18", function () {
    const s = pm.response.json().series;
    pm.expect(s[s.length - 1].date).to.eql("2026-09-18");
});"""),
        req("TC-API-003 Friday holiday closes the week on Thursday", "POST", "/v1/rsi",
            {"prices": no_friday, "freq": "W", "n": 1}, status("TC-API-003", 200) + """
pm.test("TC-API-003 weekly dates", function () {
    const d = pm.response.json().series.map(function (p) { return p.date; });
    pm.expect(d).to.eql(["2026-09-04", "2026-09-10", "2026-09-18"]);
});"""),
        req("TC-NUM-009 RSI of a steady rise is 100", "POST", "/v1/rsi", {"prices": series(range(1, 31))},
            status("TC-NUM-009", 200) + """
pm.test("TC-NUM-009 last RSI 100 and first value after 14 changes", function () {
    const s = pm.response.json().series;
    pm.expect(s[s.length - 1].rsi).to.eql(100);
    pm.expect(s[13].rsi).to.eql(null);
    pm.expect(s[14].rsi).to.be.a("number");
});"""),
        req("TC-API-010 Unknown route uses the envelope", "GET", "/nope", tests=error("TC-API-010", "NOT_FOUND", 404)),
        req("TC-API-010 Wrong method uses the envelope", "GET", "/v1/macd",
            tests=error("TC-API-010", "METHOD_NOT_ALLOWED", 405)),
    ]
    return {"info": {"name": "MACD Signal API", "schema":
                     "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                     "description": "Contract and numerical checks. Request names carry test case IDs."},
            "event": [{"listen": "test", "script": {"type": "text/javascript",
                                                    "exec": COLLECTION_TESTS.strip().splitlines()}}],
            "item": items}


def main():
    (HERE / "macd-signal-api.postman_collection.json").write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    env = {"name": "local", "values": [{"key": "baseUrl", "value": "http://localhost:8000", "enabled": True}]}
    (HERE / "local.postman_environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    print(f"wrote collection with {len(build()['item'])} requests")


if __name__ == "__main__":
    main()
