# Universe, daily screen and setup score

All strategy thresholds live in `moowoo/config.py`. No model calls are made.
Install the declared dependencies in the existing `.venv`; invoke commands with
`.venv\Scripts\python.exe` on Windows. Do not use the blocked `pytest.exe` launcher.

## Universe

`python scripts/build_universe.py --date 2026-11-16` discovers the union of current
S&P 500, S&P MidCap 400 and Nasdaq-100 constituents through `pandas.read_html`.
Nasdaq's table is now on Wikipedia's `List_of_NASDAQ-100_companies` page.
Only a successful fetch of all three tables refreshes `config/seed_tickers.txt`.
If any table fails, the entire checked-in seed is used and the error is recorded.
Class-share dots become Yahoo hyphens. This is a current constituent snapshot,
not a historical constituent database.

The freeze uses completed price sessions strictly before the supplied date.
Thus the 16 Nov freeze uses prices through 13 Nov, avoiding a partial US session.
Yahoo fundamentals are current snapshots with retrieval timestamps, not historical
fundamentals as of the requested date.

`evaluate_gates` evaluates all gates, and records the first failure in this order:

| Gate | Exact rule | Config |
| --- | --- | --- |
| Common stock | `quoteType == EQUITY` | `STOCK_QUOTE_TYPE` |
| US listing | exchange in NYQ, NMS, NGM, NCM, ASE, PCX, BTS | `US_EXCHANGES` |
| ADR | reject a positive ADR flag or depositary/ADR/ADS name evidence | `ADR_NAME_TERMS` |
| Market cap | >= US$5 billion | `GATES.marketCap` |
| Float | >= 50 million shares | `GATES.floatShares` |
| Float fraction | float / shares outstanding >= 0.5 | `GATES.floatRatio` |
| Liquidity | mean of close × volume for 20 completed sessions >= US$50 million | `GATES.avgDollarVolume`, `VOLUME_PERIOD` |
| Price | last close >= US$5 | `GATES.lastClose` |

Missing values fail the relevant gate. A missing or nonpositive shares denominator
fails float fraction. Unknown ADR status is the explicit exception to missing-value
rejection, because the brief says “if detectable”; it remains null in the output.
Yahoo's EQUITY label plus listing/name checks is a best-effort stock classification,
not an authoritative security master.

`CORE_ETFS` lists USMV, XLP, XLV, IEF and GLD. They are checked separately against
the same US$50 million average-dollar-volume threshold and never enter the stock
passing list. `config/universe-<date>.json` includes all values, all gate results,
first failures, counts, provenance, ETF checks, and a SHA-256 of the sorted passing
list encoded with the event contract's compact canonical JSON (no newline).
The expected 450–650 names is a sanity expectation, never a quota or relaxed gate.

## Data access

`get_daily_bars(tickers, start, end)` returns a ticker-to-DataFrame mapping, with
inclusive start/end dates and lowercase OHLCV. Yahoo's raw historical OHLCV is
split-adjusted; `auto_adjust=False` avoids dividend adjustments. Each frame has
`attrs.source = "yfinance"`; failed tickers have an empty frame and an
`attrs.unavailable` reason. Each failed fetch gets one retry (`DATA_ATTEMPTS = 2`).
Cache keys include ticker, dates and adjustment convention. JSON caches and Yahoo
cookie/timezone caches are under ignored `.cache/`; current-day ranges are not
cached to avoid retaining partial bars. Missing fundamentals remain null.
`get_earnings_dates` returns a list-compatible `EarningsDates` object with `.source`
and `.error`, including for empty results. Earnings are best effort, not guaranteed.

## Indicators and screen

`atr` returns Wilder ATR with an arithmetic mean of the first 14 true ranges as its
seed, followed by `(previous ATR × 13 + TR) / 14` (`ATR_PERIOD`). The first bar's TR
is high minus low. `ema` uses recursive span-20 EMA seeded at the first close and
only exposes values after 20 observations (`EMA_PERIOD`).

`rvol` divides today's volume by the **prior** 20-session mean (`VOLUME_PERIOD`).
`move_z` computes today's close-to-close return and open/prior-close gap, dividing
each by the sample standard deviation (`STD_DDOF = 1`) of the **prior** 20 daily
returns (`MOVE_PERIOD`). At least 22 closes are required. It selects the larger
absolute z, preserving its sign; ties choose the close return. `movePct` is that
selected move in percentage points. Insufficient history and zero denominators
produce unavailable indicators and a recorded screen skip, never infinity.

The screen slices supplied bars through the as-of date, then asserts the cutoff.
A ticker without a bar exactly on that date is skipped rather than screening an
old move. Candidates require `abs(z) >= 2` (`MOVE_MIN_Z`). Rank earnings movers
first, then descending `abs(z) * min(rvol, 3)` (`RVOL_CAP`); ticker sorts ties.
Earnings qualifies when its date equals either of the ticker's last two observed
session dates (`EARNINGS_SESSIONS`); future earnings dates do not qualify. It is
date-level attribution, not an intraday claim about when the release was known.
The first 15 become `picked` (`PICK_COUNT`). Earnings lookup errors are reported.

```powershell
.venv\Scripts\python.exe scripts/screen.py --universe config/universe-2026-11-16.json --asof 2026-11-13 --log .cache/2026-11-13-us.jsonl
```

This command appends exactly one `screen` event through `EventLog` and prints all
candidates with pick markers. The event includes universe and screen dates.
Using the 16 Nov universe for the requested 13 Nov diagnostic is allowed, but is
not a point-in-time universe backtest. Subsequent invocations append another event.

## Setup score

`setup_score(df, side="long")` accepts chronologically sorted, unique, finite
daily bars through the caller's as-of date. It returns total 0–5 and a boolean plus
evidence for each point. Other sides are rejected. No future data may be supplied.

1. **Trend:** latest close strictly above EMA20 (`EMA_PERIOD`).
2. **Level:** during any of the last three sessions (`LEVEL_SESSIONS`), low within
   one ATR (`LEVEL_ATR_DISTANCE`) of support and close strictly above support, or
   close crosses above resistance from at/below it on the prior session. Support:
   pre-gap close of an unfilled open-above-prior-close gap from the last 60 sessions
   (`GAP_WINDOW`); lowest confirmed swing low in the last 20 (`SWING_WINDOW`);
   EMA20. A gap is filled if any low from its formation through the tested session
   reaches its pre-gap close. Resistance is the highest confirmed swing high in
   the prior session's trailing 20-session window. Levels are recomputed at each
   tested session, never using a later bar to confirm an earlier setup.
3. **Trendline:** latest close strictly above the descending line extrapolated
   from the last two confirmed swing highs in the last 20 sessions. Both swings
   require strictly higher highs than two bars on each side (`SWING_RADIUS = 2`);
   swing lows use the opposite inequality. Line slope uses session positions.
4. **Candle:** at least one of: hammer with nonzero body, lower wick >= 2×body,
   upper wick <= body, close in top third (`HAMMER_*`); bullish engulfing with a
   red prior bar and green latest body covering the entire prior body (equal
   boundaries allowed); green momentum candle with body >= 70% of range and
   range >= 1.5×latest ATR (`MOMENTUM_*`). A zero-range candle earns no pattern.
5. **Volume:** latest volume >= 1.5×the prior 20-session mean
   (`VOLUME_MULTIPLIER`, `VOLUME_PERIOD`). The prior mean must be positive.

Checklist adapted from the Trade with Stan course notes (The.Trading.Channel);
ideas only. A score is a deterministic description, not a forecast or order.

## Validation

`python -m pytest` exercises synthetic bars, gate boundaries/missing fields,
indicator arithmetic, no-lookahead screening, earnings ordering, candle and level
near misses, trendline/volume points, provider retries/cache, and EventLog output.
The new tests replace the Yahoo provider so they cannot access the network.

The initial implementation run on 16 Nov 2026 was blocked at NumPy import by
Windows Application Control (`_multiarray_umath`). The pre-existing 64 ledger
tests passed before adding the strategy tests; the full suite cannot collect the
new module until the dependency is approved. No real universe output or screen
table has been fabricated. The checked-in 918-ticker seed was fetched successfully
from all three Wikipedia tables with Python's standard library as a bootstrap;
the production discovery path uses `pandas.read_html` as specified.
