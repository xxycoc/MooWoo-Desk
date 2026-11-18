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

Written on 18 November 2026 at about 00:05 Singapore on 19 November (11:05 New York), during the
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
