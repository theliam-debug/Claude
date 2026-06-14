#!/usr/bin/env python3
"""
Stress test for the Lsto equity & futures research tools.

Exercises the research package well beyond the unit tests:

1. Fuzz the payload parsers with random, partial, and pathological inputs
   (missing fields, zeros, negatives, NaN/inf, garbage strings) and assert
   they degrade gracefully instead of raising.
2. Run analyze_equity / analyze_futures over thousands of randomized cases and
   assert output invariants hold (bounded score, known rating, sorted curve,
   JSON-serializable briefs).
3. Determinism check: identical input yields identical output.
4. Throughput benchmark: cases/second for both analytics paths.

Exit code is non-zero if any invariant is violated. Run:

    python scripts/stress_test.py [--cases 5000] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import traceback
from dataclasses import dataclass, field

from derivatives_strategies.research.models import (
    EquityQuote,
    FuturesQuote,
    PriceSeries,
    ShortInterest,
    VolRegime,
)
from derivatives_strategies.research.equity import analyze_equity
from derivatives_strategies.research.futures import (
    analyze_futures,
    parse_future_symbol,
)

RATINGS = {"bullish", "constructive", "neutral", "cautious", "bearish"}
SHAPES = {"contango", "backwardation", "flat", "single-contract", "unknown"}
MONTH_CODES = "FGHJKMNQUVXZ"

# Values designed to break naive numeric code.
NASTY_NUMS = [
    0, -0.0, 1e-12, 1e15, -1e15, float("nan"), float("inf"), -float("inf"),
    "100", "", "abc", None, True, [], {},
]


@dataclass
class Results:
    checks: int = 0
    failures: list = field(default_factory=list)

    def ok(self):
        self.checks += 1

    def fail(self, where: str, detail: str):
        self.checks += 1
        self.failures.append((where, detail))


def _rand_num(rng: random.Random):
    """Return a random value, occasionally a pathological one."""
    if rng.random() < 0.25:
        return rng.choice(NASTY_NUMS)
    return round(rng.uniform(-500, 5000), 4)


def _rand_equity_payload(rng: random.Random) -> dict:
    payload = {
        "symbol": "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(rng.randint(1, 5))),
        "lastPrice": _rand_num(rng),
        "mark": _rand_num(rng),
        "bid": _rand_num(rng),
        "ask": _rand_num(rng),
        "52wHigh": _rand_num(rng),
        "52wLow": _rand_num(rng),
        "eps": _rand_num(rng),
        "peRatio": _rand_num(rng),
        "divYield": _rand_num(rng),
        "divAmount": _rand_num(rng),
        "change": _rand_num(rng),
        "changePct": _rand_num(rng),
        "volume": _rand_num(rng),
    }
    # Randomly drop a subset of keys to simulate partial responses.
    keys = list(payload.keys())
    for k in keys:
        if k != "symbol" and rng.random() < 0.3:
            del payload[k]
    return payload


def _rand_price_history(rng: random.Random) -> dict:
    n = rng.choice([0, 1, 2, 5, 30, 260, 600])
    candles = []
    px = rng.uniform(1, 1000)
    for i in range(n):
        # Occasionally inject a bad bar.
        if rng.random() < 0.1:
            candles.append({"datetime": "garbage", "close": rng.choice(NASTY_NUMS)})
            continue
        px = max(0.01, px * (1 + rng.uniform(-0.2, 0.2)))
        candles.append({
            "datetime": (1_600_000_000 + i * 86_400) * 1000,
            "open": px, "high": px * 1.05, "low": px * 0.95,
            "close": px, "volume": rng.randint(0, 10_000_000),
        })
    return {"symbol": "X", "candles": candles}


def _rand_futures_curve(rng: random.Random) -> list:
    root = "/" + "".join(rng.choice("ABCDEFGH") for _ in range(rng.randint(1, 3)))
    n = rng.randint(0, 6)
    quotes = []
    used = set()
    for _ in range(n):
        mc = rng.choice(MONTH_CODES)
        yy = rng.randint(24, 30)
        sym = f"{root}{mc}{yy}"
        if sym in used:
            continue
        used.add(sym)
        quotes.append(FuturesQuote.from_quote_payload(sym, {"symbol": sym, "mark": _rand_num(rng)}))
    # Occasionally throw in an unparseable symbol.
    if rng.random() < 0.2:
        quotes.append(FuturesQuote.from_quote_payload("JUNK", {"symbol": "JUNK", "mark": 100.0}))
    return quotes


def _is_json_serializable(obj) -> bool:
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


def _finite_or_none(x) -> bool:
    return x is None or (isinstance(x, (int, float)) and math.isfinite(x))


def fuzz_parsers(rng: random.Random, res: Results, n: int):
    """Parsers must never raise on arbitrary input."""
    for _ in range(n):
        try:
            EquityQuote.from_quote_payload("X", _rand_equity_payload(rng))
            FuturesQuote.from_quote_payload("X", {"symbol": "X", "mark": _rand_num(rng), "close": _rand_num(rng)})
            PriceSeries.from_price_history_payload("X", _rand_price_history(rng))
            ShortInterest.from_finra_payload("X", {
                "daysToCoverQuantity": _rand_num(rng),
                "currentShortPositionQuantity": _rand_num(rng),
            })
            VolRegime.from_payload({"term_structure_ratio": _rand_num(rng), "regime": rng.choice(["normal", "crisis", None])})
            parse_future_symbol("".join(rng.choice("/ABCDEFGHIJK0123456789") for _ in range(rng.randint(0, 8))))
            res.ok()
        except Exception:
            res.fail("fuzz_parsers", traceback.format_exc().splitlines()[-1])


def stress_equity(rng: random.Random, res: Results, n: int):
    for _ in range(n):
        payload = _rand_equity_payload(rng)
        quote = EquityQuote.from_quote_payload(payload.get("symbol", "X"), payload)
        series = PriceSeries.from_price_history_payload("X", _rand_price_history(rng))
        si = ShortInterest.from_finra_payload("X", {"daysToCoverQuantity": _rand_num(rng), "currentShortPositionQuantity": 1})
        vr = VolRegime.from_payload({"regime": rng.choice(["normal", "elevated", "crisis"]), "term_structure_ratio": _rand_num(rng)})
        try:
            brief = analyze_equity(quote, series=series, short_interest=si, vol_regime=vr, as_of="2026-06-14")
        except Exception:
            res.fail("analyze_equity", traceback.format_exc().splitlines()[-1])
            continue

        if not (-1.0 <= brief.score <= 1.0):
            res.fail("equity.score_bounds", f"score={brief.score!r} payload={payload}")
        elif brief.rating not in RATINGS:
            res.fail("equity.rating", f"rating={brief.rating!r}")
        elif not _is_json_serializable(brief.to_dict()):
            res.fail("equity.json", "to_dict not serializable")
        elif not brief.to_markdown().strip():
            res.fail("equity.markdown", "empty markdown")
        else:
            res.ok()


def stress_futures(rng: random.Random, res: Results, n: int):
    for _ in range(n):
        quotes = _rand_futures_curve(rng)
        vr = VolRegime.from_payload({"regime": rng.choice(["normal", "crisis"]), "term_structure_ratio": _rand_num(rng)})
        try:
            brief = analyze_futures(quotes, vol_regime=vr, as_of="2026-06-14")
        except Exception:
            res.fail("analyze_futures", traceback.format_exc().splitlines()[-1])
            continue

        ts = brief.term_structure
        expiries = [p["expiry"] for p in ts]
        if brief.shape not in SHAPES:
            res.fail("futures.shape", f"shape={brief.shape!r}")
        elif expiries != sorted(expiries):
            res.fail("futures.curve_order", f"expiries not sorted: {expiries}")
        elif not _finite_or_none(brief.annualized_roll_yield_pct):
            res.fail("futures.roll_yield", f"non-finite: {brief.annualized_roll_yield_pct}")
        elif not _is_json_serializable(brief.to_dict()):
            res.fail("futures.json", "to_dict not serializable")
        elif not brief.to_markdown().strip():
            res.fail("futures.markdown", "empty markdown")
        else:
            res.ok()


def check_determinism(res: Results):
    """Same input must produce identical output."""
    payload = {"symbol": "AAPL", "mark": 291.13, "eps": 7.46, "52wHigh": 317.4, "52wLow": 195.07}
    q = EquityQuote.from_quote_payload("AAPL", payload)
    ps = PriceSeries.from_price_history_payload("AAPL", {
        "symbol": "AAPL",
        "candles": [{"datetime": (1_600_000_000 + i * 86_400) * 1000,
                     "open": 100 + i, "high": 101 + i, "low": 99 + i,
                     "close": 100 + i, "volume": 1000} for i in range(300)],
    })
    a = analyze_equity(q, series=ps, as_of="2026-06-14").to_dict()
    b = analyze_equity(q, series=ps, as_of="2026-06-14").to_dict()
    if json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True):
        res.ok()
    else:
        res.fail("determinism", "equity brief not deterministic")


def benchmark(rng: random.Random, n: int) -> dict:
    # Pre-build inputs so we time the analytics, not the RNG.
    eq_inputs = []
    for _ in range(n):
        p = _rand_equity_payload(rng)
        eq_inputs.append((
            EquityQuote.from_quote_payload(p.get("symbol", "X"), p),
            PriceSeries.from_price_history_payload("X", _rand_price_history(rng)),
        ))
    fut_inputs = [_rand_futures_curve(rng) for _ in range(n)]

    t0 = time.perf_counter()
    for q, s in eq_inputs:
        analyze_equity(q, series=s, as_of="2026-06-14")
    t1 = time.perf_counter()
    for quotes in fut_inputs:
        analyze_futures(quotes, as_of="2026-06-14")
    t2 = time.perf_counter()

    return {
        "equity_cases": n,
        "equity_seconds": round(t1 - t0, 4),
        "equity_per_sec": round(n / (t1 - t0)) if t1 > t0 else None,
        "futures_cases": n,
        "futures_seconds": round(t2 - t1, 4),
        "futures_per_sec": round(n / (t2 - t1)) if t2 > t1 else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Research tools stress test")
    ap.add_argument("--cases", type=int, default=5000, help="Cases per stage")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    res = Results()
    n = args.cases

    print("=" * 64)
    print(f"Lsto Research Tools - Stress Test (seed={args.seed}, cases/stage={n})")
    print("=" * 64)

    stages = [
        ("Fuzz parsers (malformed/extreme payloads)", lambda: fuzz_parsers(rng, res, n)),
        ("Stress analyze_equity (randomized)", lambda: stress_equity(rng, res, n)),
        ("Stress analyze_futures (randomized curves)", lambda: stress_futures(rng, res, n)),
        ("Determinism", lambda: check_determinism(res)),
    ]
    for label, fn in stages:
        before = len(res.failures)
        t0 = time.perf_counter()
        fn()
        dt = time.perf_counter() - t0
        new_fail = len(res.failures) - before
        status = "PASS" if new_fail == 0 else f"FAIL ({new_fail})"
        print(f"  [{status:>9}] {label:<46} {dt:6.3f}s")

    print("-" * 64)
    bench = benchmark(rng, n)
    print("Throughput:")
    print(f"  equity : {bench['equity_per_sec']:>8,}/s  "
          f"({bench['equity_cases']:,} cases in {bench['equity_seconds']}s)")
    print(f"  futures: {bench['futures_per_sec']:>8,}/s  "
          f"({bench['futures_cases']:,} cases in {bench['futures_seconds']}s)")

    print("-" * 64)
    print(f"Total invariant checks: {res.checks:,}")
    print(f"Failures:               {len(res.failures):,}")
    if res.failures:
        print("\nFirst failures:")
        for where, detail in res.failures[:10]:
            print(f"  - {where}: {detail}")
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS  (no crashes, all invariants held)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
