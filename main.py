#!/usr/bin/env python3
"""Forecast Polymarket's next NVIDIA CEO prices, 4 hours ahead.

Program entry for make.fun competition polymarket-nvidia-ceo-forecast-01.
Python 3.13, standard library only, no network, fully deterministic.

Reads every <id>.in in the input directory (MAKEFUN_INPUT_DIR, else
/input) and writes <id>.out to the output directory (MAKEFUN_OUTPUT_DIR,
else /output): for each market and each of the 240 minutes after the
checkpoint, the five quantiles [0.05, 0.25, 0.5, 0.75, 0.95] of that
minute's Yes price, each in [0, 1], non-decreasing, 6 decimals.

Method (per market, from its 72 hours of 1-minute prices):
  Prices here are probabilities that mostly sit still, then step: ~88%
  of minutes do not move at all, and the moves that do happen partly
  revert within the hour. A plain random walk with one global spread
  (the house baseline) is far too wide for the quiet markets and too
  narrow for the jumpy ones, so each market gets its own mean-reverting
  (Ornstein-Uhlenbeck) forecast:
    median(h) = L + (x - L) * exp(-kappa * h)
    sd(h)     = sigma * sqrt((1 - exp(-2*kappa*h)) / (2*kappa))
    q_tau(h)  = median(h) + z_tau * sd(h), clamped to [0, 1]
  where x is the price at the checkpoint, L the median price of the
  last 12 hours (the level the price reverts toward), kappa set so
  10% of the gap to L closes over 240 minutes, and sigma the market's
  own recent volatility: 0.6 times the root-mean-square of its last
  one-minute moves, each move winsorized at +/-0.02 (so one wild
  tick cannot blow up the spread), floored at 0.0002 and capped at
  0.005, blended 80% from the last 2 hours with 20% from the last
  12 hours, so the spread tracks the current regime without chasing
  a single quiet or wild hour. No drift is added: recent trends did
  not continue in the practice. The spread saturates with horizon
  (unlike a random walk's), because the jumps that move these prices
  mostly revert instead of adding up.
"""
import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722]

# Mean reversion: 10% of the gap to the recent level closes in 240 min.
REVERT_240 = 0.10
KAPPA = -math.log(1.0 - REVERT_240) / 240.0
# Recent level: median price of the last 12 hours.
LEVEL_WINDOW = 720
# Volatility: 2-hour and 12-hour windows of 1-minute moves, winsorized.
SIGMA_WINDOW_SHORT = 120
SIGMA_WINDOW_LONG = 720
SIGMA_WINSOR = 0.02
SIGMA_SCALE = 0.6
SIGMA_BLEND_SHORT = 0.8
SIGMA_FLOOR = 0.0002
SIGMA_CAP = 0.005


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("empty price list")
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def price6(x):
    """Clamp to [0, 1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def _sigma_window(prices, window):
    """RMS of winsorized 1-minute moves over the last `window` minutes."""
    n = len(prices)
    if n < 2:
        return SIGMA_FLOOR
    start = max(0, n - window - 1)
    total = 0.0
    count = 0
    for i in range(start, n - 1):
        d = prices[i + 1] - prices[i]
        if d > SIGMA_WINSOR:
            d = SIGMA_WINSOR
        elif d < -SIGMA_WINSOR:
            d = -SIGMA_WINSOR
        total += d * d
        count += 1
    if count == 0:
        return SIGMA_FLOOR
    sig = SIGMA_SCALE * math.sqrt(total / count)
    if sig < SIGMA_FLOOR:
        return SIGMA_FLOOR
    if sig > SIGMA_CAP:
        return SIGMA_CAP
    return sig


def market_sigma(prices):
    """Per-market diffusion sigma: mostly the last 2 hours, steadied
    by the last 12 hours."""
    short = _sigma_window(prices, SIGMA_WINDOW_SHORT)
    long = _sigma_window(prices, SIGMA_WINDOW_LONG)
    return SIGMA_BLEND_SHORT * short + (1.0 - SIGMA_BLEND_SHORT) * long


def forecast_market(prices, horizon):
    """240 rows x 5 quantiles for one market."""
    if not prices:
        raise ValueError("market has no prices")
    x = prices[-1]
    level = median(prices[-LEVEL_WINDOW:])
    sigma = market_sigma(prices)
    rows = []
    for h in range(1, horizon + 1):
        decay = math.exp(-KAPPA * h)
        mu = level + (x - level) * decay
        var = sigma * sigma * (1.0 - math.exp(-2.0 * KAPPA * h)) / (2.0 * KAPPA)
        sd = math.sqrt(var) if var > 0.0 else 0.0
        row = [price6(mu + z * sd) for z in Z]
        rows.append(row)
    return rows


def main():
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    inputs = sorted(p for p in in_dir.iterdir()
                    if p.is_file() and p.name.endswith(".in"))
    for path in inputs:
        case_id = path.name[:-3]
        with open(path, "r", encoding="utf-8") as fh:
            case = json.load(fh)
        if case["quantiles"] != QUANTILES:
            raise ValueError(f"{path.name} asks for quantiles "
                             f"{case['quantiles']}, not {QUANTILES}")
        horizon = int(case["horizon_minutes"])
        forecasts = []
        for m in case["markets"]:
            q = forecast_market(m["prices"], horizon)
            forecasts.append({"id": m["id"], "q": q})
        payload = json.dumps({"forecasts": forecasts},
                             separators=(",", ":")) + "\n"
        out_path = out_dir / f"{case_id}.out"
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(payload)


if __name__ == "__main__":
    main()
