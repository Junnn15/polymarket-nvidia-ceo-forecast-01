# NVIDIA CEO price forecast — make.fun entry

Forecasts the Yes price of every market of Polymarket's event
"Next CEO of NVIDIA?" at every minute of the 4 hours after each
checkpoint, as five quantiles [0.05, 0.25, 0.5, 0.75, 0.95].
Entry for make.fun competition `polymarket-nvidia-ceo-forecast-01`.

## Run

```sh
python3 main.py            # reads /input, writes /output
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network, deterministic:
the same case always produces byte-identical output.

## Method

Each market gets its own mean-reverting (Ornstein–Uhlenbeck) forecast
from its 72 hours of 1-minute prices:

```
median(h) = L + (x - L) * exp(-kappa * h)
sd(h)     = sigma * sqrt((1 - exp(-2*kappa*h)) / (2*kappa))
q_tau(h)  = clamp(median(h) + z_tau * sd(h), 0, 1)
```

- `x` is the price at the checkpoint; `L` is the median price of the
  last 12 hours, the level the price reverts toward; `kappa` is set so
  10% of the gap to `L` closes over 240 minutes.
- `sigma` is the market's own recent volatility: 0.6 times the
  root-mean-square of its 1-minute moves, each move winsorized at
  ±0.02, floored at 0.0002 and capped at 0.005, blended 80% from the
  last 2 hours with 20% from the last 12 hours.

Why this shape: these prices mostly sit still (~88% of minutes do not
move at all), then step, and the steps partly revert within the hour.
A single global random-walk spread (the house baseline) is far too
wide for the quiet markets and too narrow for the jumpy ones, so the
spread is per-market, recent, and saturates with horizon instead of
growing like `sqrt(h)`. No drift is added: recent trends did not
continue in the practice data.

## Local validation

A local scorer (not part of this repository) rebuilds the true
1-minute grid from Polymarket's public price history and computes
the mean pinball loss exactly as the rules describe.

Practice cases p00–p05 (the kit's six cases):

| program | mean pinball loss |
|---|---|
| house baseline (starter) | 0.363589 |
| this entry | **0.266503** |

Per case: p00 0.467, p01 0.298, p02 0.352, p03 0.239, p04 0.191,
p05 0.117. Median error 0.770, 90% coverage 0.873.

Out-of-sample check on two extra cases built from the most recent
data (checkpoints 2026-11-13T06:00Z and 10:00Z, after the practice
window): this entry 0.082 / 0.122 vs baseline 0.221 / 0.242.

Runtime is ~0.06 s per case (limit 8 s); outputs are ~250 KB
(limit 1 MiB); two runs are byte-identical.

## License

MIT — see LICENSE.
