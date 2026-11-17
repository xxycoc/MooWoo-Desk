# MooWoo Desk preregistration

Registered on 17 November 2026 for the Moomoo x Qoder AI Trading Agent Challenge.
Starting capital is simulated US$100,000. We trade US stocks and ETFs, long only,
from 17 to 27 November 2026. Final valuation uses the regular-market close on
27 November. This document must be committed before any live paper trade.

## 1. What we are testing

Large stock-specific moves explained by news tend to drift in the same direction.
Unexplained drops tend to bounce. These are hypotheses, not established facts.

The LLM's only decision is whether news explains a screened move. It records its
call, confidence, evidence and news cutoff before the outcome is known. It does
not select quantities, change limits or place discretionary orders. Code maps
explained rises to long drift trades and unexplained drops to long bounce trades.
Other directions are recorded and graded but do not authorize short selling.
Risk checks may veto any entry. The price-action setup score is logged only.

## 2. What the history check already showed

The price-only study used earnings as a proxy for explained news. FIT covered
1 December 2023 to 31 October 2025. HOLDOUT covered 1 November 2025 to
13 November 2026. FIT alone selected `abnormal-D3-R2-B2`: at least 100 drift
and 100 bounce trades, then the highest trade-weighted mean excess return;
ties used grid order. HOLDOUT did not select the parameters.

For the selected combined strategy, HOLDOUT had 990 trades. Mean excess return
over matched SPY windows was **-0.1903042505%**, with a 95% bootstrap interval
of **[-0.4837145521%, +0.0985207804%]**. These figures come from
`chosen.periods.HOLDOUT.combined` in the history-check JSON.

The interval includes zero. Price rules alone showed no established holdout edge.
Any claimed edge from reading news must therefore be tested in live paper trading.
The history check did not test an LLM. Setup-score results were not monotonic, so
the score will not drive sizing.

## 3. Frozen setup

| Item | Frozen reference |
| --- | --- |
| Universe | `config/universe-2026-11-16.json`, 727 passing stocks |
| Passing-list SHA-256 | `c9233c06ef87c4d83f68688c06e5136c881b6f78bf643377fd5e8dd0482f5e4e` |
| Configuration | `config/frozen-2026-11-17.json` |
| configHash | `9c1c03d43e142c29788b01947f3c4b6c2ea8206dd074b10c885bb905ae9ed6b4` |
| Code provenance | The frozen file's `gitCommit` identifies the prior code commit, not the later document commit. |
| Prompt version | `pending` |

The frozen file contains every public value in `moowoo/config.py`, the universe
reference, the history-check file hash and chosen variant, and the code commit.
Its hash is SHA-256 of canonical JSON excluding `configHash` itself.
Prompts will be frozen and their hash appended in a dated addendum before the
first live order. Pending prompts do not authorize trading. This registration
specifies intended trading behavior; configuration data alone does not implement
or verify an executor or broker risk checks.

| Strategy setting | Rule |
| --- | --- |
| Move mode | `abnormal`: 60 prior trading days of stock/SPY returns; screen at absolute z >= 2. |
| Drift | `K_drift = 3` ATR stop; `R_drift = 2` minimum relative volume; at most 5 sessions. |
| Bounce | `K_bounce = 2` ATR stop; target the pre-drop close; at most 3 sessions. |
| Core | 50% target in USMV, XLP, XLV, IEF and GLD. Weights are proportional to inverse daily-return volatility over 60 completed trading days. |
| Core rebalance | Rebalance when absolute actual-minus-target weight divided by target weight reaches 0.25. |
| Satellite | At most 25% initially; at most 40% after the step-up test below. |
| Cash | Whatever remains, at least 10%. Caps are ceilings, not required investment. |
| Setup score | `log_only`; never used for sizing. |

Core ETF weights sum to the 50% core target. The 8% per-name cap below applies
to satellite stocks, not core ETFs. Applying it to five ETFs would prevent a 50%
core allocation. Missing or invalid data cannot authorize a new entry.

| Risk setting | Limit |
| --- | --- |
| Per satellite stock | 8% of equity. |
| Daily loss | Halt new entries at a 1.5% loss from session-start equity. Exits remain allowed. |
| Peak-equity tiers | At -2% drawdown: reduced sizing. At -4%: exits only. At -6%: kill, cancel entries and liquidate. The strictest triggered state wins. |
| Orders | At most 30 per session; none in the first 5 regular-market minutes. |
| Spread | At most 0.15% of midpoint. |
| Liquidity | Order notional at most 0.5% of prior 20-session average daily dollar volume. |
| Correlation | New satellite positions must have 60-day daily-return correlation <= 0.80 with existing satellite positions. |
| Price freshness | At most 60 seconds old at order checks. |
| Bounce concentration | At most 3 simultaneous bounce positions. |
| Trailing stop | Arm after a 1 ATR favorable move; trail by 1.5 ATR; never loosen an existing stop. |
| Quick-tier call | Half the otherwise permitted size. |
| Final day | No new entries on 27 November 2026. Mark remaining positions at that day's regular-market close. |

The regime filter is on if SPY's latest completed daily close is below either its
20-day EMA or its 100-day SMA, or if its 5-day realized volatility is at least
twice its 20-day realized volatility. Volatility uses sample standard deviation
of daily close returns. When on, stop new bounce trades and cap the satellite
at 20%, even after step-up. Existing positions keep their exit rules. Daily loss,
drawdown and other stricter risk limits always override allocation targets.

## 4. Hypotheses, metrics and exact verdicts

We log rated movers and skips, not just successful trades. Calls cannot be
deleted after an outcome. The grading record includes the ticker, decision time,
news cutoff, forecast direction, horizon and confidence before grading starts.
An explained call forecasts continuation of the screened move over 5 sessions.
An unexplained call forecasts reversal over 3 sessions. Grade from the next
regular-session open to the horizon close, truncated at the final valuation close.
A forecast is right only if stock return minus matched SPY return has the
forecast sign; zero counts as wrong. This measures usefulness of the call, not
independent proof of news causation. Calls without observable entry/outcome
prices stay ungraded and are counted as missing, never silently removed.

### H1: classification

Graded calls, both traded and skipped, are right more than 50% of the time.
Report the hit rate and its 95% Wilson interval.

| Verdict | Exact rule |
| --- | --- |
| supported | Interval lower bound > 50%. |
| rejected | Interval upper bound < 50%. |
| can't tell yet | Otherwise, including no graded calls. |

### H2: value over simple rules

The LLM book's mean excess return over SPY beats both follow-all and fade-all.
Use the same rated screened-mover decision IDs, entry opportunities, costs and
exit rules in all three books. Follow-all buys rises using drift rules. Fade-all
buys drops using bounce rules. Neither book shorts; ineligible directions and
skipped allocations earn zero while in cash. The LLM book applies its calls and
the same risk constraints. Preserve vetoes and unavailable prices in the report.
These are satellite decision books; the common core cannot manufacture an H2 win.

Compute paired differences in mean excess return: LLM minus follow-all, and LLM
minus fade-all. Use 2,000 bootstrap resamples of whole entry-session clusters,
seed 20261117, preserving paired decisions within each session. Report 95%
percentile intervals. The H1 rule is applied to zero, not 50%, for differences:
**supported** only if both lower bounds > 0; **rejected** if either upper bound
< 0; otherwise **can't tell yet**. An unavailable interval means can't tell yet.

### H3: calibration

The Brier score is the mean squared error between prelogged confidence that a
forecast is right and its binary H1 outcome. The target is below 0.25, the score
of a constant 50% forecast. Report the score and a session-cluster bootstrap
interval using the H2 settings. The point-estimate target is met below 0.25 and
not met at or above 0.25. With no graded calls it is not assessable.

### Risk-adjusted results, reported regardless

Report total return, Sharpe, Sortino, Calmar and maximum drawdown for the full
account, SPY buy-and-hold and an equal-weight buy-and-hold of the frozen passing
stocks. All start at the first eligible entry time and end at the final valuation
close. The equal-weight baseline is not rebalanced. Disclose missing baseline
prices and any resulting incomplete coverage.

Use session-close account equity including cash, fills and costs. Sharpe uses
mean daily return divided by sample standard deviation, annualized by sqrt(252),
with zero risk-free rate. Sortino uses downside deviation below zero. Calmar is
annualized compounded return divided by absolute maximum drawdown. Drawdown uses
the running equity peak. Report 95% percentile intervals for every metric by
resampling paired session-return vectors 2,000 times with seed 20261117 and
rebuilding equity paths. Report zero-denominator or otherwise undefined ratios
and intervals as unavailable, not infinity. Annualized ratios over this window
are descriptive and unstable.

### Step-up and invalidation

After at least 15 graded calls, increase the satellite ceiling from 25% to 40%
only when the LLM graded-call book's mean excess return beats follow-all on the
same completed decisions so far, by point estimate. Skips remain in the matched
set as cash. Evaluate at session close; any increase starts next session and
cannot override regime or risk caps. The core remains 50% and cash at least 10%.

After at least 15 closed satellite trades, compare the LLM book with both shadow
books on the same completed decision set using mean excess return. If it trails
the better of follow-all and fade-all, stop new satellite trades for the rest of
the window. Exit existing satellite positions under their frozen rules and park
in the core, subject to risk limits, retaining unallocated cash. Do not exceed
the 50% core target to force full investment. Report the thesis as **failed**.
This invalidation overrides step-up and any favorable individual hypothesis.

## 5. How many calls we expect

We expect about 12 trade calls across 8 traded sessions, plus skipped calls that
are graded. This is an estimate, not a quota or a reason to relax screening.
The window contains about 7.5 full-session equivalents. It can detect only a
large edge. Fifteen graded calls or closed trades may never be reached. Shared
market shocks make calls dependent and the effective sample smaller.

## 6. What may change during the window

Changes require a dated rule-ledger entry with the old rule, new rule, reason,
supporting decision IDs and effective session. They apply no earlier than the
next session and never loosen a risk limit. Keep the original freeze and record
the replacement hash. The specified step-up is an existing conditional rule,
not permission to loosen another limit. Prompt hashes must be added before
the first live order. Anything else is a deviation and will be reported as one.

## 7. Limitations

- Survivorship bias: the frozen universe uses current, not historical, membership.
- Earnings are an incomplete news proxy. Missing dates can mislabel moves.
- Yahoo prices, fundamentals and earnings may be incomplete or wrong. Historical
  bars are split-adjusted, not dividend-adjusted; daily bars hide intraday paths.
- The history check used independent overlapping trades, not a cash-constrained
  US$100,000 portfolio. Its trade-bootstrap intervals can be too narrow.
- Paper fills need not match executable prices, queue position or market impact.
- The short live window has low statistical power. Bootstrap intervals based on
  so few sessions are fragile. No result establishes dependable future profit.

## 8. Credits

Price-action checklist ideas came from the Trade with Stan course notes. They
are logged, not used for sizing. The debate structure was inspired by
TradingAgents (Xiao et al., 2024). No code from either source is used.

## 9. Addendum 2026-11-17: prompts frozen before the first order

Written on 17 November 2026, before any order in the competition account.

- promptVersion `e96f044a0a4fae7692deac96757da0bd7a601429e686738eefb93db76a280ec0`: SHA-256 of `agents/*/system.md`, `schemas/rating.schema.json`
  and `agents/permissions.json`, computed by `scripts/hash_prompts.py` at commit `baa8acc`.
  Every `run_started` event must carry this value; the preflight guard refuses orders otherwise.
- Changes since the prompts were first written: the quick classifier's reason is limited
  to 3 sentences and 400 characters, after one evaluation answer ran to 750; the
  coordinator and auditor follow the numbered `scripts/run_session.py` phases. Classes,
  sizing, risk limits, horizons, grading and hypotheses H1 to H3 are unchanged.
- Schedule: the morning run is 09:35 New York (22:35 Singapore), after the
  first-five-minutes rule. The first plan said 21:30 Singapore, which is premarket in New York; the
  regular-hours guard would have skipped it. Watchers run every 30 minutes from 10:00
  to 16:00 New York; the audit runs 10 minutes after each close. Orders are regular
  hours only, although the challenge allows 04:00 to 20:00 New York.
- AUTONOMY-01 (`config/rule-ledger.jsonl`): the executor places paper orders without
  per-order human approval from the first session. Controls stay in code: risk desk,
  preflight guard, ticket verification halt, real-money tools disabled with no trade scope,
  drawdown tiers, daily loss halt and kill switch.
- Evidence: the raw hash-chained ledger lives in a private repository during the window,
  so live positions cannot be copied, and is published in full after 27 November.
