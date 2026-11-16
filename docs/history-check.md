# Price-half history check

Earnings is a proxy for explained news, and non-earnings is a proxy for unexplained moves. This does not backtest news classification.

FIT: 1 Dec 2023–31 Oct 2025. HOLDOUT: 1 Nov 2025–13 Nov 2026. Replay uses the live as-of screener, its earnings-first rank, and top 15 each day. The 24 variants combine raw/abnormal moves, drift stops 2/2.5/3 ATR, drift RVOL 1.5/2, and bounce stops 2/2.5 ATR. FIT alone selects highest trade-weighted mean excess, requiring 100 trades in each strategy. Ties use grid order.

Enter next open; pay 5 bps each side. Drift holds at most five sessions; bounce targets the pre-drop close and holds at most three. Stop wins if target and stop share a bar. Gap-through fills use open. Signal ATR is fixed; trailing updates apply next session and never fall. Support is the highest setup-score level at/below signal close; absent support uses the ATR stop. Trades needing a full holding window beyond a period end are omitted. SPY buys at the same entry open and sells at the exit-day close, including costs; exact intraday SPY matching is unavailable.

Coverage: 727/727 names with bars; 727 reach 13 Nov 2026. Earnings: 724 names, 8847 name-quarters (13 distinct calendar quarters). No earnings record is treated as unexplained, so incomplete coverage biases both ranking and labels.

Each cell: trades / mean net return / mean excess over SPY [95% interval]. Intervals use 2,000 trade resamples, seed 20261116; overlapping and same-day trades are dependent, so these intervals can be too narrow.

| Strategy | FIT | HOLDOUT |
|---|---|---|
| drift | 1035 / 0.49% / 0.12% [-0.17%, 0.39%] | 546 / -0.07% / -0.22% [-0.67%, 0.24%] |
| bounce | 827 / -0.04% / -0.04% [-0.25%, 0.18%] | 444 / -0.06% / -0.15% [-0.50%, 0.19%] |
| combined | 1862 / 0.26% / 0.05% [-0.12%, 0.25%] | 990 / -0.06% / -0.19% [-0.48%, 0.10%] |
| SPY (combined windows) | 1862 / 0.21% / 0.00% [0.00%, 0.00%] | 990 / 0.13% / 0.00% [0.00%, 0.00%] |
| follow-all | 3078 / 0.47% / 0.16% [-0.04%, 0.35%] | 1801 / 0.25% / 0.22% [-0.08%, 0.51%] |
| fade-all | 3138 / 0.08% / -0.02% [-0.16%, 0.11%] | 1802 / 0.11% / 0.06% [-0.15%, 0.26%] |

FIT-selected parameters: `{"MOVE_MODE": "abnormal", "K_drift": 3, "R_drift": 2, "K_bounce": 2}`. These were adopted as live defaults in the 17 Nov preregistration; they were not changed during the history-check run.
The holdout edge is weak or absent: positive excess is not established by its interval. These parameters are a FIT selection, not evidence of reliable profit.

| Setup score | FIT | HOLDOUT |
|---|---|---|
| 0-2 | 740 / -0.04% / -0.08% [-0.31%, 0.15%] | 416 / 0.21% / 0.10% [-0.23%, 0.46%] |
| 3 | 615 / 0.48% / 0.27% [-0.07%, 0.61%] | 297 / -0.38% / -0.62% [-1.21%, 0.03%] |
| 4-5 | 507 / 0.43% / -0.02% [-0.45%, 0.41%] | 277 / -0.14% / -0.17% [-0.77%, 0.44%] |

Score pattern: FIT: not monotonic; HOLDOUT: not monotonic. Do not use the score for sizing: the 4–5 bucket does not beat 0–2 on both periods. This is a secondary descriptive check.

Raw versus abnormal (daily candidate counts: mean / 95th percentile / maximum):
- raw, FIT: 53.18 / 143 / 606
- raw, HOLDOUT: 52.93 / 130 / 315
- abnormal, FIT: 39.32 / 104 / 389
- abnormal, HOLDOUT: 45.24 / 102 / 373

| Best eligible FIT variant within mode | FIT | HOLDOUT unchanged |
|---|---|---|
| raw-D2-R2-B2 | 1915 / 0.15% / -0.06% [-0.24%, 0.12%] | 1012 / -0.17% / -0.23% [-0.51%, 0.06%] |
| abnormal-D3-R2-B2 | 1862 / 0.26% / 0.05% [-0.12%, 0.25%] | 990 / -0.06% / -0.19% [-0.48%, 0.10%] |

Abnormal mode estimates OLS beta with intercept and residual standard error (n−2) on prior 60 close returns; subtracts beta × SPY move from close and gap, without subtracting intercept. Raw uses prior 20 returns. Their first warm-up dates differ; the requested November data start cannot supply 60 returns for early FIT.

Limitations: Survivorship bias: today's frozen constituents, not historical membership. Earnings dates proxy for explained news; non-earnings dates proxy for unexplained moves. This tests prices, not the LLM/news rule. Missing earnings can mislabel explained moves. Daily bars cannot reveal intraday paths; stop wins when stop and target share a bar. Yahoo bars and earnings can be incomplete or wrong; split-adjusted, not dividend-adjusted prices are used. Independent overlapping trades, equal weight per trade; no $100,000 portfolio, capacity, or cash constraint is simulated.

Run: 2026-11-16T16:47:01.992204+00:00; 2632.0 seconds. Coverage, hashes, all metrics and grid results are in `config/history-check-2026-11-16.json`; every simulated trade and signal score is in `config/history-trades-2026-11-16.jsonl.gz`.
