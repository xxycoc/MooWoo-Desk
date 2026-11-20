# Offline risk desk

This desk converts ratings and account data into deterministic paper-order tickets.
It makes no network or broker calls. The LLM supplies a classification and confidence;
it cannot choose quantities, change a ticket or place discretionary orders.

## Pipeline

1. **Rating:** a prelogged `decisionId`, ticker, class, confidence in [0, 1] and
   `debate` or `quick` tier. Only `explained_up` maps to drift and
   `unexplained_down` to bounce. Other classes produce logged skips.
2. **Proposal:** exits first, then core rebalances (sells before buys), then
   satellite entries, then the 30% SPY beta sleeve from remaining cash. Code supplies whole-share quantity, cent-rounded limit,
   initial stop and fixed signal ATR. Setup score never affects sizing.
3. **Verdict:** `risk.check(proposal, state, market)` returns `approve`, `resize`
   or `veto`, ordered `rules`, detailed `checks`, the first `firedRule`, and
   `qtyAfter` (zero on veto). All gates are evaluated for audit evidence; the
   earliest failure remains the first fired rule even if a later gate vetoes.
4. **Ticket:** approved quantities become immutable, hash-checked `OrderTicket`s.
   Pending buys reserve exposure and cash including fees. Pending sells do not
   release cash or exposure before fills. Planning never pretends a fill happened.
5. **Executor:** separately verifies the prompt freeze, account, current risk and
   exact adapter arguments before placing an order. This build contains no executor.
   The manifest says `executionAuthorized: false`; risk approval alone does not
   satisfy the preregistration's pending-prompt requirement.
6. **Reconciliation:** compare placed arguments with `verify_placed`, then use
   cumulative broker-status fills with `reconcile_fill`. An auditor must apply
   actual fills to positions/cash, remove completed/cancelled reservations and
   preserve ticketed IDs. Reconciliation here calculates results; it does not
   mutate a portfolio or call a broker.

## Frozen rules and fee addendum

`config/frozen-2026-11-17.json` stays byte-for-byte unchanged. Its `configHash`
remains the strategy reference on every ticket. `config/rule-ledger.jsonl` holds
FEES-01, dated 2026-11-17 and effective from the first session. The planner checks
both the original canonical hash and exact equality between current configuration
and the frozen values plus this authorized four-key addendum. Unknown or modified
values refuse planning.

| New config key | USD value | Meaning |
| --- | ---: | --- |
| `FEE_PER_ORDER` | 0.99 | One platform fee per filled order |
| `FEE_PER_SHARE_SOLD` | 0.000166 | Additional fee per share sold |
| `FEE_SELL_CAP` | 8.30 | Cap on the per-share selling fee per trade |
| `MIN_ENTRY_NOTIONAL` | 2,000 | Minimum final whole-share buy notional |

Buy fee = 0.99. Sell fee = 0.99 + min(8.30, 0.000166 ? quantity).
Thus the maximum sell estimate is 9.29. Fees retain their decimal precision;
only order prices are rounded to cents. An unfilled order has no realized fee.
The flat fee is charged once across cumulative partial fills, not per update.
`fees.realized_pnl` computes a completed buy/sell round trip after both fees;
`reconcile_fill.cashDelta` also includes fees. Net excess returns supplied to
step-up checks must include the same costs in all matched books.

Any entry below 2,000 after rounding is skipped with `below_min_notional`;
a risk resize below that floor becomes a veto. The buy platform fee is at most
4.95 bps at the floor. Exits have no minimum. The archived FIT/HOLDOUT study in
`history.py` retains its disclosed 5-bps-per-side historical cost assumption;
FEES-01 applies prospectively and does not rewrite the frozen study or its results.

## Sizing and core

Satellite notional = `PER_NAME_CAP` ? equity ? confidence ?
min(1, 0.02 / sample daily-return SD over 20 completed sessions), multiplied by
`QUICK_TIER_SIZE_FACTOR` (0.5) for quick ratings and another 0.5 in reduced tier.
Whole shares round down. Confidence is never treated as permission to exceed a cap.

Drift requires RVOL >= `R_drift` (2). Bounce requires RVOL < `RVOL_CAP` (3) and
either close above EMA20 or support at/below close within one signal ATR. Support
is the highest qualifying level from `setup_score.support_levels`. Stops are
max(support minus ATR, entry minus K ? ATR), with `K_drift` = 3 and `K_bounce` = 2.
If support is absent, use the ATR stop. Bounce target is the pre-drop close.
Reject entries already through their stop or bounce target. Store `signalAtr`
and `preDropClose` on proposals and tickets.

Buy limit uses ask, or last ? 1.001 when ask is absent. Sell limit uses bid,
or last ? 0.999. Round half up to a cent. An entry still needs a valid bid/ask
spread at the risk gate; a last-only sizing quote does not waive that gate.

Core ETFs are `CORE_ETFS`: USMV, XLP, XLV, IEF and GLD. Inverse sample
volatilities over `CORE_VOLATILITY_PERIOD` = 60 daily returns (61 closes) give
weights summing to `CORE_WEIGHT` = 0.30. Dates must align. Missing, zero or invalid
volatility refuses the allocation. Buy initially; rebalance when
abs(actual weight minus target weight) / target weight >= `CORE_REBALANCE_BAND`
= 0.25. Core proposals pass the same risk checks, except the satellite-only gates.

## Ordered risk gates

Threshold equality is allowed for maxima unless explicitly described as a halt.
Missing or invalid data needed by an entry gate fails closed at that gate.

| Order | Rule | Threshold and config key | Action |
| ---: | --- | --- | --- |
| 1 | `kill_or_halted` | `tier == kill` or halted | Veto entry |
| 2 | `exits_only` | `tier == exits_only` | Veto entry |
| 3 | `daily_loss` | Loss >= `DAILY_LOSS_HALT` = 1.5% from session-start equity, or latched daily halt | Veto entry |
| 4 | `final_day` | `NO_NEW_ENTRIES_ON_FINAL_DAY`; session >= `FINAL_DAY` = 2026-11-27 | Veto entry |
| 5 | `first_minutes` | Elapsed < `NO_ORDERS_FIRST_MINUTES` = 5; also refuse entries outside the supplied regular session | Veto entry |
| 6 | `regime` | Bounce blocked by `REGIME_STOP_BOUNCE`; satellite ceiling `REGIME_SATELLITE_CAP` = 40% | Veto bounce; resize drift |
| 7 | `duplicate_decision` | ID already in `ticketedDecisionIds` | Veto buy or sell |
| 8 | `max_orders` | Submitted count plus current-session unsubmitted reservations >= `MAX_ORDERS_PER_SESSION` = 30 | Veto entry |
| 9 | `stale_price` | Quote age > `STALE_PRICE_SECONDS` = 60, or future timestamp | Veto entry |
| 10 | `spread` | (ask - bid) / midpoint > `MAX_SPREAD` = 0.005 | Veto entry |
| 11 | `correlation` | Pearson correlation > `MAX_CORRELATION` = 0.80 over `CORRELATION_PERIOD` = 60 aligned daily returns against another open/pending satellite name | Veto entry |
| 12 | `bounce_count` | A new bounce name would exceed `MAX_BOUNCE_POSITIONS` = 3, including pending buys | Veto entry |
| 13 | `satellite_invalidated` | Thesis invalidated; block new satellite exposure | Veto entry |
| 14 | `per_name_cap` | Satellite stock exposure > `PER_NAME_CAP` = 20% of marked equity; core and beta ETFs exempt | Resize |
| 15 | `ticker_cap` | Held + pending BUY + new shares at ticket limit <= `MAX_TICKER_VALUE` = USD 40,000, all sleeves | Resize or drop |
| 16 | `satellite_cap` | `SATELLITE_CAP` = 60%, or `SATELLITE_CAP_STEP_UP` = 60% once effective; regime 40% still wins | Resize |
| 17 | `cash_floor` | Cash after pending buys, proposed buy and fees must retain `CASH_FLOOR` = 10% of equity | Resize |
| 18 | `adv` | Notional <= `MAX_ADV_FRACTION` = 0.005 times average close times volume over prior `VOLUME_PERIOD` = 20 completed sessions | Resize |

Invalidation runs directly after bounce count, before the pure resize rules, so
an oversized invalidated entry reports invalidation rather than a resize as its
first failure. The earlier mixed regime gate retains its preregistered position.
`core_target` follows these gates and limits core buys to the 30% aggregate target
on the projected post-sell planning state. `beta_target` follows it and limits
SPY buys to 30% including pending buys and fees. Both sleeves share all account
halts, final-day restrictions and entry checks; satellite-only gates do not apply.
Finally,
`below_min_notional` vetoes undersized buys even when no resize was needed.
Every resize rounds down. Below one share or below the entry floor means veto.
A resize-triggered veto retains that resizing rule as `firedRule`.

Sells bypass every entry gate, including daily loss, kill, first minutes, freshness,
order count and allocation limits. Only duplicate IDs block a valid exit. Invalid
sell requests exceeding held shares less pending sells raise an input error;
this enforces long-only accounting rather than blocking a valid exit.

The regime is on if SPY close is below either `REGIME_EMA_PERIOD` = 20 EMA or
`REGIME_SMA_PERIOD` = 100 SMA, or short volatility over `REGIME_VOL_SHORT_PERIOD`
= 5 is >= `REGIME_VOL_MULTIPLIER` = 2 times long volatility over
`REGIME_VOL_LONG_PERIOD` = 20. Use `REGIME_BENCHMARK` = SPY and sample SD
(`STD_DDOF` = 1). It never changes existing positions' exit rules.

## Tiers, exits and step-up

`TIERS` uses drawdown from the running peak: reduced at -2%, exits_only at -4%,
kill at -6%. Tightening is immediate; the strictest state wins. Recovery requires
one full observed session inside the better band. Recovery beginning intraday
cannot loosen at that close; it can loosen at the following close if it persists.
Recovery observed at the open can loosen at that session's close. A breach resets
the wait. `update` returns `tier_changed` and `halt` payloads.

Kill latches `halted`, requests entry cancellation and liquidation. Only
`state.restart(nonempty_written_reason)` clears it, records the reason and returns
a halt-clear payload to log. It leaves the tier at exits_only pending recovery;
continued -6% drawdown immediately kills again. Daily loss is a separate latch:
blocks entries for the session, resets next session, never blocks exits.

Equity is cash plus positions marked at supplied prices. Snapshot JSON preserves
`cash`, ticker-keyed `positions`, `sessionStartEquity`, `peakEquity`,
`ordersPlacedThisSession`, `sessionDate`, `tier`, `halted`, `haltReason`,
`dailyLossHalted`, recovery fields, `stepUp`, ticketed IDs, reservations and restart
reasons. Each position carries qty, avgCost, sleeve, kind, entryDate, entryPrice,
stop, trailArmed, highestClose, preDropClose, signalAtr and decisionId. Persist
returned exit updates including `lastExitCheck`; replay does not reprocess bars.
Supply the actual session-start equity, not a newly sampled intraday value.

Exit checks use the fixed signal ATR. Existing stop wins if stop and target both
occur in a daily bar, matching `history.py`. Drift trailing arms at close >= entry
+ `TRAIL_ARM_ATR` (1) ? ATR, then raises the stop to highest close minus `TRAIL_ATR`
(1.5) ? ATR, never lowers it. A close update applies after that bar's stop check.
Latest quotes also trigger stops or bounce targets. Completed holding sessions
trigger time exits at `DRIFT_MAX_SESSIONS` = 5 or `BOUNCE_MAX_SESSIONS` = 3.
FINAL-CLOSE-01: only realised results count. On 27 Nov, no BUYs are permitted in
any sleeve, including cash-funded core rebalances and SPY. From
`FINAL_LIQUIDATION_FROM` = 12:00 New York, morning/watch runs propose "final liquidation"
SELLs for every holding, net of pending sells. Reconcile and cancel unfilled orders,
then retry remaining quantities at 12:30 and 12:55 before the 13:00 early close.
Time exits and protective exits remain active before noon. Final-liquidation limits
are 1% below the current bid (last price fallback), rounded down to cents, to allow
price movement during dispatch. Ordinary exits retain their existing limit pricing.
Fresh-quote marketability checks still apply; a limit order cannot guarantee a fill.
Daily-loss and drawdown halts do not block final liquidation, but unrelated safety
halts still do. Open BUYs are listed for cancellation; unsubmitted BUYs are skipped.

TICKER-CAP-01: `MAX_TICKER_VALUE` = USD 40,000 is an absolute BUY backstop for all
sleeves. Held + pending BUY + new shares, all valued at the new ticket limit, must
fit under the cap. Pending SELLs do not create room until filled, including during
conditional core rebalancing. Shrink to whole shares or drop if zero (the existing
minimum-entry-notional gate still applies). Dispatch rechecks the cap.

At session close, `stepup.evaluate` compares matched decision IDs. At least
`STEP_UP_MIN_GRADED_CALLS` = 15 graded calls and mean LLM net excess > follow-all
permits 40% starting next supplied trading session. Skips count as cash outcomes;
missing paired values prevent a decision. At least 15 closed satellite trades and
mean LLM net excess below the better of follow-all/fade-all permanently invalidate
the satellite thesis for this window. Invalidation overrides step-up, preserves
normal exits and never raises the core target above 30%. Evidence lists counts, decision
IDs, missing IDs and book means. The caller supplies net, fee-inclusive outcomes.

## Tickets and partial fills

A ticket contains `decisionId` (idempotency key, <= 100 UTF-8 bytes), `ticker`,
`side`, `qty`, `limitPrice`, `sleeve`, `kind`, `stop`, `reason`, `estFees`,
`configHash`, `createdTs`, `signalAtr`, `preDropClose` and `ticketHash`.
The hash is SHA-256 of canonical JSON excluding `ticketHash`. Deserialization
checks the hash and fee estimate. Resizing recalculates fees for approved quantity.

`to_sim_order(ticket, acc_id=None, market=None)` requires `MOOMOO_ACCOUNT_ID`
and `MOOMOO_MARKET` in the environment even when arguments are supplied;
explicit arguments must match. It returns only the exact MCP arguments:
`acc_id` as string, `market` as integer (100 means US margin),
`symbol = US.<TICKER>`, `order_type = 1`, `order_side = 1` buy or `2` sell,
`qty`, `price`, and `text = decisionId`. `format_symbol` is the single symbol
formatter. `verify_placed` returns `ok` and exact expected/observed mismatches,
including missing and unexpected arguments.

Competition section 7 allows partial fills when market volume ? 20 is below order
quantity. This module does not predict broker fills from daily bars.
`reconcile_fill(ticket, filled_qty, avg_price, status, at_session_close=False)`
uses cumulative observed fills and returns `filled`, `partial` or `unfilled`,
remaining quantity, actual fees and cash delta. It rejects overfills and fills
outside the approved limit. At session close, pass `at_session_close=True`:
any remaining quantity sets `cancel_leftover=True`. This flag requests executor
cancellation; it does not claim a cancellation occurred. Apply differences between
successive cumulative results, never the full cumulative cash delta twice.

## Offline CLI and audit

```powershell
.venv/Scripts/python scripts/plan_session.py --state state.json --ratings ratings.json --bars-asof 2026-11-16 --bars cached-bars.json --quotes quotes.json --log ledger/2026-11-17-us.jsonl
```

Bars may be a ticker-keyed JSON object of chronological OHLCV rows with `date`,
a directory of ticker JSON files, or cached pandas-table wrappers. Only completed
bars through `--bars-asof` are used, and each accepted series must end on that date.
Default bars path is `.cache/desk/bars.json`. Quotes JSON supplies `sessionDate`,
`now`, `regularOpen`, `regularClose` (timezone-aware), and ticker-keyed `quotes`
containing `last`, `bid`, `ask`, `ts`. Supply the actual exchange schedule including
the final day's early close. The CLI does not fetch a trading calendar.

Optional `--graded-calls`, `--closed-trades`, `--next-session` enable close-time
step-up evaluation. At or after the supplied close, use completed session data.
`--tickets-dir` defaults to `tickets`; output is `<runId>.json`. State and manifest
writes are atomic. EventLog is append-only and hash chained. Serialize writers.

Every proposal appends `order_intent` then `risk_verdict`; approved verdicts embed
`approvedTicket`. Skips use `reflection_note` with `skipped: true`, source and
reason. Tier/halt payloads use existing event types. Core target evidence uses
`core_rebalance`. These are allowed extensions to the v0 event contract.
The verified log reconstructs missing reservations/tickets after interruption,
without inventing fills. Repeated IDs never produce a second ticket. Kill manifests
list `cancelEntryDecisionIds`; the executor must honor them before submission.

`drills.run_drills` checks stale quotes, a proposal three times the per-name cap,
duplicate replay, and -6% shadow equity. Each writes only a marked `drill` event
with expected, observed and pass values. Original state is unchanged; no drill
creates a ticket. Run all offline checks with `.venv/Scripts/python -m pytest`.

## SLEEVE-01 and cash-funded rebalancing

Allocation is core 30% + SPY 30% + satellites + a 10% cash floor. SPY is
orderable only as sleeve/kind `beta`; the frozen stock universe is unchanged.
The morning order is core sells, core buys, satellite entries, then SPY.
`propose_beta` uses the same 25% relative target band, buys only with actual
cash left after other pending buys and fees, and trims only above the band.
Satellite entries never liquidate SPY or anticipate its proceeds. Core and
SPY have no stop, trailing stop or horizon exit; kill liquidation still applies.

At dispatch, the core exposure allowance is 30% of effective equity plus the
current value of this session's planned core sells that remain unfilled.
Filled quantities are deducted using reconciliation checkpoints. All pending
buys and fees still reserve cash, and the 10% cash floor is unchanged. If sells
never fill, temporary core overweight is accepted until the next morning's
rebalance. Without sufficient actual cash, core buys still require full
reconciled core sells. Beta buys always require actual cash and their own target.
