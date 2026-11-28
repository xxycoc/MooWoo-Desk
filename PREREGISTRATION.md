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

## 10. Addendum 2026-11-17: clock duty moves to the coordinator

Written on 17 November 2026 at about 23:00 Singapore, still before any order in the competition account.

- promptVersion `7ee7873b161e09e7c38c7398ed19a6ed8e171d6b747231beca1d64d694a09a12`, computed by
  `scripts/hash_prompts.py` from the same files as Addendum 9. It replaces `e96f044a...`.
- Why: both runs on 17 November halted before preflight with no broker orders. The scheduled
  09:35 New York run stopped on a parser bug (wrapped account list, fixed in `4719f43`). A manual
  rerun, logged as off-schedule in its session message, stopped because the coordinator asked the
  executor to verify the clock, and the executor has no clock tool.
- Change: the coordinator checks the time with `date -u` before each external call and states the
  verified UTC time when it delegates; the executor no longer halts only because it cannot read a
  clock. The runner still enforces the lease (`require_owned`) and ticket freshness in code.
  Classes, sizing, risk limits, horizons, grading and hypotheses H1 to H3 are unchanged.
## 11. Addendum 2026-11-17: barsAsOf comes from the frozen calendar

Written on 17 November 2026 at about 23:10 Singapore, still before any order in the competition account.

- promptVersion `9742d80fd83db2e36e9b7768e7f970dcf46fd363b113e67d2445f26027948397`, computed by `scripts/hash_prompts.py`. It replaces `7ee7873b...`.
- Why: the second manual rerun passed preflight and reconciliation, then halted because the
  coordinator tried to prove the previous session (Friday 14 November) from news searches; the
  calendar listed only 17 to 27 November.
- Change: `moowoo/calendar.py` records 14 November 2026 as a completed full session, and
  `scripts/session_info.py` prints barsAsOf and session hours from the frozen calendar. The
  coordinator uses it and does not research the exchange calendar. No rule, class, sizing,
  risk limit, horizon, grading or hypothesis changes.
- Correction, 23:17 Singapore: 14 November 2026 was a Saturday. The completed session before 17 November is Monday 16 November, and the calendar now records that date. The third rerun halted correctly when every stock lacked a bar for 14 November; it did not substitute a date.

## 12. Addendum 2026-11-18: fixed handoffs between agents

Written on 18 November 2026 at about 01:00 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `b9fd4ebecb05338d173e55ddaf2a448af9cfe0ae6dcbb0f51ffc0c593d2744d7`, computed by
  `scripts/hash_prompts.py`. It replaces `9742d80f...`.
- Why: six runs on 17 November halted before any order. A read-only review of their saved evidence found one
  cause behind most halts: procedures written as prose, so the coordinator improvised duties (asking the executor
  to check the clock or write files, researching the calendar through news) and child agents refused them.
- Change: the coordinator follows an exact command sequence (`session_info.py`, `gather_inputs.py`,
  `ingest_ratings.py`, `convert_quotes.py`, `dispatch_check.py` before each order, and the `run_session.py`
  phases). It is the only file writer and owns clock checks. Child agents never write files or check time.
  The executor follows AUTONOMY-01 and returns receipts in the shape `record` expects. Unavailable model-cost
  data is recorded as missing, never as zero.
- Code fixes in the same change: log identity comes from events rather than filenames; positions accept
  decimal strings; a lease can be renewed while unexpired, up to 120 minutes per run, and the morning session
  timeout is 120 minutes. The 60-second price freshness rule is unchanged.
- No class, sizing, risk limit, horizon, grading or hypothesis changes.

## 13. Addendum 2026-11-18: five movers a day (PICKS-01)

Written on 18 November 2026 at about 01:50 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `983b7102efeb0fe4907f1d55c6cf2107a2e320a3e5029ad814a30accb55adf50`, computed by
  `scripts/hash_prompts.py`. It replaces `b9fd4ebe...`.
- Decided by Siang Woo: the screen picks at most 5 movers a day instead of 15 (`PICK_COUNT`, rule
  `PICKS-01` in `config/rule-ledger.jsonl`). Every pick gets the bull, bear and manager debate, and quick
  gives an independent second opinion on each. The quick-only primary route for ranks 6 to 15 is gone.
- Why: about 45 model calls per morning run would not reliably fit the run lease; 5 movers need about 25.
- Effect on the study: fewer rated calls per day, so hypotheses H1 to H3 and the 15-graded-call step-up
  will take longer to reach their sample sizes. Classes, sizing, risk limits, horizons and grading are unchanged.

## 14. Addendum 2026-11-18: briefs go inline to the no-tool agents

Written on 18 November 2026 at about 01:55 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `fc75156efca9faa6c330ec37e7a746947dbd0e2dd13a2fd02737f770717fcf0a`, computed by `scripts/hash_prompts.py`. It replaces `983b7102...`.
- Why: rerun 7 reached the debate with five picks, then the coordinator gave the ARMK bear agent a file path
  instead of the brief text. Bear has no tools, could not read it, and the coordinator aborted the whole run.
- Change: the coordinator pastes the full brief (and, for manager, the bull and bear replies) inline for bull,
  bear, manager and quick. One child's failed or unusable reply is only that ticker's logged skip; the run
  continues. No rule, class, sizing, risk limit, horizon, grading or hypothesis changes.

## 15. Addendum 2026-11-18: a closed list of abort reasons

Written on 18 November 2026 at about 02:20 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `616b8953707864df5d420a052d536628bd4eab4e0e6eb948032d48b2d27ed1be`, computed by `scripts/hash_prompts.py`. It replaces `fc75156e...`.
- Why: rerun 8 reached the debate, then the coordinator aborted after it caught and corrected its own copying
  slip in a saved analyst reply. Most halts on 17 November were the coordinator judging, on its own, that
  something justified stopping.
- Change: the coordinator aborts only for a failing deterministic command, lease expiry or lost ownership, an
  account or routing mismatch, or a broker or persistence error during execution. Its own file slips are
  rewritten from the original reply; a child's failed or missing reply is that ticker's logged skip; it never
  waits idle while holding the lease. No rule, class, sizing, risk limit, horizon, grading or hypothesis changes.

## 16. Addendum 2026-11-18: keep the coordinator's context small

Written on 18 November 2026 at about 03:10 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `a09024d009fba94c1774207df3b3e467354adafc67eddfa807496b1e6ba73d6b`, computed by
  `scripts/hash_prompts.py`. It replaces `616b8953...`.
- Why: rerun 9 reached the debate for all five picks, then every coordinator model request timed out (504,
  no response within 63 seconds) from about 02:41 Singapore while new sessions answered normally. Its
  conversation held about 268,000 characters: 78,000 from reading reference docs, 58,000 from the Write
  tool echoing saved files back, and 61,000 of debate briefs.
- Change: the coordinator does not read docs, the pre-registration, schemas, agent prompts or scripts; it reads
  only this run's JSON outputs, prints only what it needs, and saves files with shell heredocs. The scheduled
  start message no longer points to `docs/runtime.md`. No rule, class, sizing, risk limit, horizon, grading or
  hypothesis changes.

## 17. Addendum 2026-11-18: one ticker per call, quotes converted on arrival

Written on 18 November 2026 at about 03:45 Singapore (17 November in New York), still before any order in the competition account.

- promptVersion `e02740ee9a77ba501ea840d456e3fd60b47cba72363ed88328deb0f75510d265`, computed by `scripts/hash_prompts.py`. It replaces `a09024d0...`.
- Why: rerun 10 completed the debate and reached quotes, but every rating was skipped. The coordinator sent
  all five tickers to bull in one message and the reply covered only TSN; the TSN manager wrapped its JSON in
  prose. Then quote conversion refused the live reply, whose rows sit under `data.snapshot_list` with
  `update_time` in epoch milliseconds, and the run aborted with no orders.
- Change: one ticker per child call; quotes are converted in the same step as they are saved, with one fresh
  retry before a conversion failure counts as an abort. Code fixes in the same change (no promptVersion effect):
  `convert_quotes.py` reads `snapshot_list` and epoch-millisecond times, and `parse_rating` accepts exactly one
  JSON object embedded in prose, logging a warning. The 60-second freshness rule is unchanged.
- No rule, class, sizing, risk limit, horizon, grading or hypothesis changes.
- Addendum 17 note, 04:00 Singapore: the coordinator now runs on the `efficient` model instead of `ultimate`
  (`agents/coordinator/agent.json`; promptVersion unchanged). Reruns 9 and 11 stalled when every coordinator
  request timed out once the debate replies arrived, while small watcher sessions on the same model answered.
  The coordinator rates nothing; analyst, bull, bear, manager and executor stay on `ultimate`, quick on `efficient`.

## 18. Addendum 2026-11-18: strict JSON boundary kept; model provenance from config

Written on 18 November 2026 at about 04:55 Singapore (17 November in New York), after the US close. No order
has been placed in the competition account.

- promptVersion `02487d0bb7d90300dc2fc29092d88a142b160a48ca505499ed1b591902e9d75b`, computed by
  `scripts/hash_prompts.py`. It replaces `e02740ee...`.
- Correction to addendum 17: the change that let `parse_rating` pull one JSON object out of prose broke the
  pre-freeze tests `test_malformed_json_stays_rejected`, which encode the rule that prose-wrapped output is
  malformed. It is reverted. Instead, manager and quick are told their entire reply is the one JSON object.
- Why: rerun 12 (coordinator on `efficient`) completed research and debate in about 20 minutes, but every
  primary rating was rejected only because agents reply `model: null`; they cannot see their deployment model id.
  `ingest_ratings.py` now fills a null `model` from the deployed agent definition (`agents/<role>/agent.json`).
  Quotes then went stale twice (about 138 seconds old after the analyst's slow reply), and Qoder's cap of 25
  concurrent agents blocked two manager calls.
- Change: the analyst answers quote requests with a single tool call and an immediate reply; the coordinator
  runs at most 10 child calls at once. The 60-second freshness rule is unchanged. No rule, class, sizing,
  risk limit, horizon, grading or hypothesis changes.

## 19. Addendum 2026-11-18: three agents, one rater per pick, fresh quote per order

Written on 18 November 2026 at about 14:45 Singapore (01:45 New York), before the 18 November session. No
order has been placed in the competition account, and no rating was ever accepted under the debate design.

- promptVersion `3776d9e16c6afff1f14e4e5c36297178f2522c2f1920e470298bed93be1f932f`, computed by
  `scripts/hash_prompts.py`. It replaces `02487d0b...`.
- Why: all 13 attempts on 17 November halted before an order. Most later failures came from the coordinator
  relaying briefs between seven agents (25 child calls a morning): briefs sent as file paths, batched calls,
  model timeouts as its context grew past 180k characters, and Qoder's 25-agent concurrency cap. The
  organisers advised starting with two or three agents that communicate in one direction.
- Rule change TOPOLOGY-01 (rule ledger): the morning uses three agents. The analyst researches each pick and
  returns one rating in a new tier `single`, sized exactly like the former `debate` tier; no risk limit
  changes. Bull, bear, manager and quick are retired, so there is no debate and no quick second opinion. The
  hypotheses are tested on `single` ratings; claims about debate versus quick, and about second opinions, are
  dropped. Historical `debate` and `quick` tiers stay valid in the schema.
- Execution: before each order the analyst fetches one fresh quote for that symbol, and `dispatch_check.py`
  requires its source time to be at most 60 seconds old and the code-derived limit price to be unchanged.
  Before this change dispatch measured ticket age, so a quote could reach about 110 seconds. The 60-second
  rule itself is unchanged. Each receipt is recorded immediately; abort records saved receipts and releases
  reservations of tickets never handed to the executor.
- Fixes with no rule change: ingestion enforces `PICK_COUNT` and fills `model` only when the key is present
  and null; the coordinator waits up to 10 minutes per pick instead of marking running calls unavailable;
  renewal reports when the 120-minute cap is reached; audits require a competition trading day; on the entry
  day, exit checks use only the close, because that day's open, high and low may precede the fill.

## 20. Addendum 2026-11-18: short quote replies; the 18 November run used the wrong code revision

Written on 18 November 2026 at about 23:50 Singapore (10:50 New York), during the
18 November session. No order has been placed in the competition account.

- promptVersion `5524e3574e7b0675b94bba0ffacf7bc3c9e07b6c8a35cd0d4c42071f9e20e028`, computed by
  `scripts/hash_prompts.py`. It replaces `3776d9e1...`.
- What happened: the scheduled 09:35 run (`2026-11-18-morning-8a3264191cb9`) ran the addendum 19 prompts on
  the previous code revision `8ee921d`, because the deployment's pinned `REPO_REVISION` was not updated. The
  cloud setup's prompt-hash check therefore failed. The old ingestion expected manager and quick files, so all
  five single-rater replies (ACM, NKE, ED, UNH, CRM) were skipped, and two quote batches were 173 to 196 seconds
  old at conversion, so the run aborted safely with no order. Its evidence and log are kept in the ledger.
- Why the quotes were old: the analyst copied the full snapshot (dozens of fields per symbol) into its reply in
  about 100 seconds, and the coordinator copied it again into a file in about 75 seconds.
- Change: for quote tasks the analyst returns only the envelope status and, per symbol, `code`, `update_time`,
  `last_price`, `bid_price` and `ask_price`, each copied exactly from the tool result; the coordinator saves
  it and converts or checks it in the same command. These are the only fields the converter and dispatch check
  read. The 60-second rule is unchanged. No rule, class, sizing, risk limit, horizon, grading or hypothesis
  changes. A rerun on the correct revision today is off-schedule and is logged as such.

## 21. Addendum 2026-11-19: a prepared limit only has to stay marketable at dispatch

Written on 19 November 2026 at about 00:15 Singapore (18 November, 11:15 New York), during the 18 November
session, after the off-schedule rerun `2026-11-18-morning-d32bc89ad591`. That rerun accepted all five ratings
(ACM, NKE, ED, UNH, CRM) and placed the first order of the competition: buy 218 IEF at limit 90.62, accepted
by the broker and not yet filled at reconciliation.

- promptVersion `5524e3574e7b0675b94bba0ffacf7bc3c9e07b6c8a35cd0d4c42071f9e20e028`, unchanged from addendum 20;
  this addendum changes code only.
- Why: addendum 19 required the code-derived limit price to equal one recomputed from the fresh dispatch quote.
  In the rerun, four of five core tickets (USMV, XLP, XLV, GLD) were skipped because the quote had moved by a
  cent between planning and dispatch.
- Change: the prepared limit price is never changed. At dispatch a buy proceeds only if the fresh ask-derived
  limit is at or below the ticket's limit, and a sell only if the fresh bid-derived limit is at or above it.
  A buy never pays more, and a sell never accepts less, than planned. The 60-second source-time rule, the
  spread rule, sizing and every other rule are unchanged.
- Also fixed: the cloud setup's test run failed because a fresh clone had no `.pytest_tmp` folder; the code the
  run executes was not affected.
- Observed: the coordinator reported text in Qoder agent notifications asking it to create a one-time schedule.
  It is not in the session event log or in any agent reply, and the coordinator ignored it as untrusted data.

## 22. Addendum 2026-11-19: more capital to satellite trades (SIZING-01); live position fields

Written on 19 November 2026 at about 00:45 Singapore (18 November, 11:45 New York), during the 18 November
session. Holdings: 218 IEF bought at 90.62 (core), filled after the rerun's reconciliation.

- promptVersion `5524e3574e7b0675b94bba0ffacf7bc3c9e07b6c8a35cd0d4c42071f9e20e028`, unchanged; this addendum
  changes configuration and code only.
- Rule change SIZING-01 (rule ledger), decided by Siang Woo with six sessions left: core weight 0.50 to 0.30;
  satellite cap 0.25 to 0.60 and its step-up cap 0.40 to 0.60; per-name cap, which also sets each entry's
  size, 0.08 to 0.20 of equity; maximum entry spread 0.15% to 0.5% of the midpoint. Unchanged: stops and
  trailing stops, horizons, drawdown tiers, the daily loss halt, the kill switch, the 0.20 regime satellite
  cap, the 10% cash floor, long-only, classes and grading. The defensive core cannot reach the leaderboard's
  returns, so capital moves to the rated movers. This raises risk and is reported separately from results
  under the original sizing. Effective from the first session after 19 November 01:00 Singapore (the 01:00 watcher onward).
- Fix: the first live position snapshot names average cost `cost_price` and the current price `cur_price`,
  not the provisional `avg_cost` and `market_price`, so the 00:30 Singapore watcher halted at preflight with
  nothing changed. The mapping now uses the live names. Replaying that watcher's inputs offline reconciles with
  no difference and no halt.

## 23. Addendum 2026-11-19: reconciliation tolerance scales with position value

Written on 19 November 2026 at about 01:45 Singapore (18 November, 12:45 New York), during the 18 November
session, after the off-schedule entry run `2026-11-18-morning-ebd4816e4caf` under SIZING-01.

- promptVersion `5524e3574e7b0675b94bba0ffacf7bc3c9e07b6c8a35cd0d4c42071f9e20e028`, unchanged; code only.
- That run filled the first satellite trade (ACM, 130 at 83.049, drift from explained_up) and a core buy
  (XLP, 40 at 91.62). The IEF rebalance sell was skipped for a stale quote; USMV's authorization expired before
  handoff and was never sent; XLV and GLD were vetoed by the core-target rule. Its final reconciliation halted:
  broker cash, quantities and orders matched the book exactly, but the broker's total asset priced positions
  USD 9.75 above its own position snapshot, because the two snapshots are separate calls and prices moved
  between them. The fixed USD 1 tolerance cannot hold once positions are live.
- Change: the cash/position equity check allows USD 1 or 0.25% of the marked position value, whichever is
  larger. Cash and quantities are still taken exactly from the broker; a missing or extra position still
  halts. Replaying that reconciliation offline passes with no difference. No strategy rule changes.

## 24. Addendum 2026-11-19: release authorizations that were never sent

Written on 19 November 2026 at about 02:15 Singapore (18 November, 13:15 New York), during the 18 November
session.

- promptVersion `5524e3574e7b0675b94bba0ffacf7bc3c9e07b6c8a35cd0d4c42071f9e20e028`, unchanged; code only.
- Why: in run `2026-11-18-morning-ebd4816e4caf` the USMV ticket passed its dispatch check, but its quote
  deadline passed before handoff, so the coordinator never sent it (recorded as `approval_expired`). Because
  it had been authorized, it stayed pending with its cash reserved.
- Change: reconciliation releases an authorized ticket only when the broker's complete order history has no
  order for its decision and either the handoff record says it was not submitted or its quote deadline is more
  than 15 minutes past. It logs a ticket skip and never re-dispatches that decision. Anything that may have
  reached the broker stays pending. No strategy rule changes.

## 25. Addendum 2026-11-19: input mistakes stop one run, core sells fund core buys, a working daily report

Written on 19 November 2026 at about 09:50 Singapore (18 November, 20:50 New York), between sessions.

- promptVersion `e90c070c64e7ab5cb57e4d675111d58425978ba01906bc96465ec5b0b4d594b5` (coordinator, executor and
  auditor prompts changed).
- Why: on 18 November the 15:04 New York watcher stopped with `missing required broker field: qty` because the
  coordinator dropped one field while copying order history; the broker reply was correct. The halt was saved,
  so every later run, including the close audit, refused to start until an operator restart (19 November,
  ledger commit `aadaa94`). Both close audits (17 and 18 November) produced no daily report because the
  completed bars were never saved. The core held 2 of its 5 ETFs: the rebalance sell of IEF was skipped on a
  stale quote and the core budget then vetoed the XLV and GLD buys. The 16:00 watcher always skipped itself
  because the session counts as closed at 16:00.
- Changes:
  - Broker replies are saved trimmed to the fields the parser needs and checked right after saving; the agent
    may re-fetch a bad reply twice. A malformed or missing input file now aborts only that run, with its reason
    logged, and does not set the persistent halt. Genuine broker/book disagreements still halt exactly as before.
  - A quote that fails only for age may be fetched once more and checked again. The 60-second limit and the
    duplicate-order protections are unchanged.
  - CORE-REBALANCE-01 (rule ledger): core buys may be sized after the planned core sells of the same session,
    but are authorized only after those sells have fully filled and been reconciled, and after the post-sell
    core and cash limits pass. An unfilled or partly filled sell funds nothing. The 30% core target and all
    other limits are unchanged.
  - The auditor fetches completed daily bars with one command, every audit abort logs its reason, and the report
    keeps what it can compute and lists what is missing instead of inventing numbers.
  - The close watcher moves to 15:55 New York, and to 12:55 on the 27 November early close.

## 26. Addendum 2026-11-19: an unreadable quote gets one refresh; the close audit posts to Slack

Written on 19 November 2026 at about 23:10 Singapore (10:10 New York), during the session.

- promptVersion `e90c070c64e7ab5cb57e4d675111d58425978ba01906bc96465ec5b0b4d594b5` (unchanged; no prompt edits).
- Why: in the 19 November morning run the coordinator wrote a malformed copy of the IEF quote reply
  (`Expecting ':' delimiter`) and later rewrote it correctly, but dispatch had already read the broken file and
  skipped the IEF core sell. Under CORE-REBALANCE-01 the USMV, XLV and GLD core buys then could not be authorized,
  so the core rebalance did not happen that day. The TJX satellite buy was skipped separately because the fresh
  quote moved past its limit, which is the intended behaviour.
- Changes:
  - A quote file that cannot be read or parsed now shares the existing one-refresh budget of a stale quote
    (commit `9e59566`, deployed as agent version 32): the coordinator fetches one fresh single-symbol quote and
    repeats the check; a second failure skips the ticket as before. Price past the limit, spread, symbol mismatch,
    future timestamps and CORE-REBALANCE-01 still skip at once. No limit, threshold or sizing rule changed.
  - The close audit ends with a fixed summary written by code from the daily report (commit `bade87f`, agent
    version 31), and the audit schedules deliver it to a paired Slack channel. Only the auditor, which has no
    order tools, is connected to Slack.

## 27. Addendum 2026-11-20: more of the account invested (SIZING-02, CORE-REBALANCE-02, SLEEVE-01)

Written on 20 November 2026 at about 00:30 Singapore (19 November, 11:30 New York), during the session.
Holdings: ACM 130 (satellite), IEF 218 and XLP 40 (core); cash about 66% of equity.

- promptVersion `0aa06321a360d35237eb970b08c39070e2993935b9a66893a524687402e2811e` (coordinator prompt changed:
  order of processing, and when core and SPY buys may use existing cash).
- Why: after three sessions the account held about 66% cash. Stock signals are rare (one satellite entry so far),
  the weak-regime cap of 20% was full after one entry (DIS and TGT were vetoed on 19 November), and the core
  rebalance failed on both 18 and 19 November because core buys waited for an IEF sell. Siang Woo decided that,
  for the remaining six sessions, keeping capital in the market matters more than waiting for signals.
- Rule changes (rule ledger), decided by Siang Woo on 19 November, effective from the first session after
  20 November 00:00 Singapore:
  - SIZING-02: in a weak regime satellites may use up to 40% of equity instead of 20%.
  - CORE-REBALANCE-02: core buys are authorized from existing cash when the 10% cash floor holds, without waiting
    for the same session's core sells. Until those sells fill, the core may exceed 30% by their value; an unfilled
    sell is trimmed by the next morning rebalance. If cash does not cover a buy, it still waits for reconciled sells.
  - SLEEVE-01: a new sleeve holds SPY at 30% of equity at all times, rebalanced each morning with the core band.
    It is bought only from cash left after core and satellite tickets, never sold to fund satellites, and has no
    stop, like the core. Drawdown tiers, exits-only, the kill switch and the daily loss halt treat it like the core.
- Unchanged: core 30% and its five ETFs, the 60% normal satellite cap, the 20% per-name cap, the 10% cash floor,
  stops and trailing stops, horizons, drawdown tiers, the daily loss halt, the kill switch and long-only.
- Consequence: the account becomes roughly 30% core, 30% SPY and up to 30% satellites, so daily returns now
  follow the market much more closely. SPY is also the comparison benchmark, so excess return over SPY will be
  smaller in size by construction. Results are reported separately before and after this addendum, as for
  SIZING-01. Code: commits `3f015ad` and `59ffd3e`.

## 28. Addendum 2026-11-20: close every position before the final close (FINAL-CLOSE-01, TICKER-CAP-01)

Written on 20 November 2026 at about 11:00 Singapore (19 November, 22:00 New York), between sessions.
Holdings: ACM 130 (satellite), IEF 218 and XLP 40 (core); cash about 66% of equity.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075` (coordinator prompt: final-day
  procedure; auditor prompt: optional notes are written with the file tool and cannot abort the audit).
- Why: on 20 November the organisers clarified the competition rules. Only realised results count, so every
  position must be closed before the 27 November 13:00 New York early close. Sharpe uses daily close-to-close
  account value from 17 to 27 November, as `moowoo/audit.py` already computes. No ticker may hold more than
  USD 40,000 (40% of the USD 100,000 start). This replaces the "Final day" rule in the risk table ("mark remaining positions at that day's
  regular-market close").
- Rule changes (rule ledger), effective from the first session after 20 November 00:00 Singapore:
  - FINAL-CLOSE-01: on 27 November no BUYs are placed, including core rebalances and SPY. From 12:00 New York,
    morning and watch runs sell every held quantity in every sleeve, net of pending sells, with reason
    "final liquidation". The 12:30 and 12:55 watchers retry what is left. These sells are priced at 99% of the
    bid, rounded down, and accept quotes up to 300 seconds old (the broker's last-update time on quiet ETFs lags
    60 to 150 seconds at midday). The daily loss halt and the drawdown tiers do not block them; other halts do.
    Time exits are no longer suppressed on the final day.
  - TICKER-CAP-01: a BUY is shrunk or dropped so that held shares, pending buys and the new order stay at or
    below USD 40,000 at the ticket limit price. Dispatch rechecks it.
- Auditor: the 19 November audit ended as an abort after the auditor ran an improvised Python import while
  writing optional notes. The report and Slack summary were still produced and delivered. The prompt now says
  optional steps cannot abort the audit, and the reply carries no delivery-status lines.
- Unchanged: all sizing, stops, horizons, tiers, the daily loss halt for entries, the kill switch and long-only.
- Consequence: the final equity is cash, realised before the close, rather than a mark at the close. Selling about
  one hour early gives up or avoids the last hour's move. Code: branch `fix/35-final-close`.

## 29. Addendum 2026-11-20: a price cushion on order limits (LIMIT-01)

Written on 20 November 2026 at about 23:40 Singapore (10:40 New York), during the session, after the morning
run `2026-11-20-morning-7c93b9d5e17a`.
Holdings: ACM 130 (satellite), IEF 218 and XLP 40 (core); cash about 66% of equity.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`, unchanged from addendum 28;
  this addendum changes code only.
- Why: the morning run approved eight tickets (sell 84 IEF; buy 63 USMV, 22 XLV, 9 GLD, 122 PDD, 30 WWD, 57 P
  and 23 SPY) and dispatched none. Each buy limit equalled the ask at planning, and addendum 21 skips a buy
  whenever the fresh ask is above that limit. In the one to four minutes between planning and dispatch the
  market rose: SPY 0.2%, USMV, XLV and GLD 0.13 to 0.19%, PDD 0.8%; IEF's bid fell. P was skipped for its
  spread. With no cushion the desk can only buy when the price is flat or falling.
- Change (rule ledger LIMIT-01, from the first session after 20 November 23:00 Singapore): ticket limits are
  set 0.5% above the ask for buys and 0.5% below the bid for sells. At dispatch a buy proceeds while the fresh
  ask is at or below its limit, and a sell while the fresh bid is at or above it. Orders still fill at the
  best available price. Sizing, stops and bounce targets keep using the unbuffered quote; risk checks, cash
  reservations and the ticker cap use the cushioned limit, so buys are about 0.5% smaller in shares.
  Final-liquidation sells keep their 1% cushion from addendum 28.
- Unchanged: the 60-second quote rule, the spread rule, sizing, stops, tiers and all loss limits.

## 30. Addendum 2026-11-20: the book follows the broker's diluted cost after a sale

Written on 20 November 2026 at about 23:45 Singapore (10:45 New York), during the session, after the
off-schedule rerun `2026-11-20-morning-c140f058ebb3`.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`, unchanged; code only.
- Why: the rerun, under addendum 29, dispatched its first ticket (sell 84 IEF), which filled at 91.475. The
  next reconciliation halted on "unexplained broker/book difference": quantities matched (134 IEF on both
  sides), but the book kept the average cost at 90.62 while the broker reported 90.084. Moomoo reports
  diluted cost: gross sale proceeds reduce the cost of the remaining shares, (218 x 90.62 - 84 x 91.475) / 134
  = 90.084. This was the desk's first sale, so the case had not occurred before. The other six tickets
  (USMV, XLV, GLD, WWD, P, SPY) were skipped by the abort.
- Change: on a sell fill that leaves shares, the book's average cost becomes (previous cost - gross sale
  proceeds) / remaining shares, matching the broker. Entry prices, stops and trailing logic are unchanged.
  Quantity, cash and missing-position checks are unchanged.
- Operator action: the run halt was cleared by an operator restart after this fix was deployed, and the morning
  session was rerun once.

## 31. Addendum 2026-11-26: closed broker rows and part-filled orders no longer stop the desk

Written on 26 November 2026 at about 22:30 Singapore (09:30 New York), during the Thanksgiving market
holiday, after every session on 25 November aborted.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`, unchanged; code only.
- Why: the 25 November morning run `2026-11-25-morning-2c22f7e3a63a` placed the time exit for ACM (sell 130,
  limit 79.79). Two broker behaviours that had not occurred before then stopped the desk:
  1. While the order was resting and partly filled, Moomoo's order history listed it as 70 shares with
     `cum_qty` 0; the 60 sold shares showed only in the positions list. Reconciliation raised
     "order history mismatch: qty" and the book halted.
  2. After the order completed (130 at 80.724), Moomoo kept a closed ACM row with `qty` 0 and
     `cost_price` 0. The positions validator rejected the zero cost, so all 12 later watchers and the
     audit aborted before preflight. No orders were placed or cancelled by any of them.
- Change:
  1. A broker position row with zero shares is treated as closed and dropped; open rows are validated as before.
  2. If a submitted order is still resting (observed status 2) and the broker lists fewer shares than the
     ticket with no fill reported, reconciliation treats the order as in flight. The book and the pending
     ticket stay unchanged until the broker reports the completed order, which is then applied as normal.
     The broker's position must differ from the book by exactly the implied filled shares, and cash must
     move in the right direction within the order's limit price plus a 10% band; anything else still halts.
     Every other quantity mismatch still halts.
- Verification: the real 25 November broker replies (history, positions, cash) replayed through the fixed
  reconciliation give no difference. The book drops ACM and its cash matches the broker's 21,563.17.
- Operator action: the 25 November halt is cleared by an operator restart after deployment, before the
  27 November morning run. No session is rerun; the market is closed on 26 November.

## 32. Addendum 2026-11-28: the final sell-off did not run; no trades after the window

Written on 28 November 2026 at about 10:00 Singapore, after the window closed. No rule or code changes.
This records an outcome and an operator decision.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`, unchanged.
- What happened on 27 November:
  1. The morning run reconciled the 25 November ACM sale (130 at 80.724) as Addendum 31 intended, placed
     no buys and finished cleanly.
  2. The 12:00 New York watcher, which had to start FINAL-CLOSE-01, aborted before planning:
     `convert_quotes.py` rejected the planning quote batch twice because the USMV quote was older than
     60 seconds. The 12:30 watcher aborted for the same reason (106 seconds old).
  3. The 12:55 watcher started at 12:57 and reached its calendar check at 13:00:25, after the early
     close, and skipped.
  4. No final-day order was placed. Nine holdings stayed open: GLD 9, IEF 134, NVDA 22, PDD 97, SPY 42,
     USMV 63, WWD 24, XLP 40, XLV 22. The 13:10 audit reconciled with no difference and reported
     FINAL-CLOSE-01 as not completed.
- Cause: Addendum 28 allowed final-liquidation quotes up to 300 seconds old, but only the per-ticket
  dispatch check used that limit. The earlier planning quote conversion kept the general 60-second limit
  with no final-day exception, so one quiet ETF blocked every sell. No test covered the final-day
  planning path. The same 60-second abort had occurred on earlier days and was treated as harmless
  because the next watcher ran; on the last day there were only three attempts.
- Result at the 27 November close: account value USD 101,942.17 (broker total), USD 101,980.54 marked
  at session closes in `docs/results.md`. Realised result about −USD 242 (ACM −302.25, IEF part-sale
  +71.82, all fees −11.91); the rest is unrealised in the nine holdings.
- Operator decision: the organiser said actions after the competition date are the entrant's decision.
  We place no trades after 27 November, so every reported number comes from 17-27 November and every
  trade on record was authorised by the desk's code. All schedules were paused on 28 November.

## 33. Addendum 2026-11-28: the ledger is published as a masked copy

Written on 28 November 2026, after the window closed. No rule or code changes to the desk.

- promptVersion `000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`, unchanged.
- Section 9 promised to publish the raw hash-chained ledger in full after 27 November. The raw
  ledger holds broker order IDs and other long identifiers that this project never publishes, so
  publishing it unchanged is not possible.
- Published instead: [`ledger-public/`](ledger-public/README.md), made by `scripts/mask_ledger.py`
  from the private ledger branch at commit `2a2b1e92c2ba26afe07505d1950eafe7fa776f6f`. It holds all
  155 run logs (742 events), the order tickets, the daily audit reports and the hypothesis settings.
- Masking: every standalone run of seven or more digits becomes `***` plus its last four digits;
  `hash`, `prevHash`, `runId`, `sourceRunId` and `decisionId` are unchanged. Before masking, every
  private log verified. After masking, the 660 unmasked events still verify against their own hashes
  and every chain link is intact; the 82 masked events are listed in `ledger-public/MANIFEST.json`,
  with the SHA-256 of each private file, and verify only against the private copy.
- Not published: raw broker payloads (input snapshots, order receipts), agent hand-off files and the
  runtime state file. Their effects are recorded as events in the published logs.
