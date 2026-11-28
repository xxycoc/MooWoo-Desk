# MooWoo Desk results

Paper trading only, US stocks and ETFs, long only. Returns are fractions unless a value is shown with a percent sign.

## Daily equity

| Day | Equity (USD) | Source |
| --- | ---: | --- |
| 2026-11-17 | 100,000.00 | rebuilt close (after-close audit cash and positions × session close) |
| 2026-11-18 | 99,903.36 | rebuilt close (after-close audit cash and positions × session close) |
| 2026-11-19 | 99,624.86 | rebuilt close (after-close audit cash and positions × session close) |
| 2026-11-20 | 98,562.37 | audit report |
| 2026-11-23 | 101,322.04 | audit report |
| 2026-11-24 | 101,074.17 | audit report |
| 2026-11-25 | 101,086.21 | after-close audit broker total |
| 2026-11-27 | 101,980.54 | audit report |

Latest data day: 2026-11-27.
No missing days: every session has a reconciled audit report or a broker snapshot.

## Account metrics

- Total return: 1.98%
- Sharpe (annualised): 3.44
- Sortino (annualised): 9.95
- Calmar (annualised): 59.46
- Max drawdown: -1.44%

Annualised ratios over about eight sessions are unstable and descriptive only.

## Mean daily return

- Mean daily return: 0.25%
- 95% bootstrap interval: -0.37% to 1.11% (10,000 resamples, seed 7).

## SPY comparison

- SPY return from the 2026-11-17 regular-session open to the 2026-11-27 close: -1.36%.

## Preregistered hypotheses

- H1: matched 50; hit rate 52.00%; 95% interval 38.51% to 65.20%; verdict can't tell yet.
- H2: matched 0; mean excess follow unavailable, fade unavailable, LLM unavailable; verdict can't tell yet.
- H3: matched 50; Brier score 0.290; 95% interval 0.237 to 0.352; verdict not met.

## Trades

| Time (ET) | Ticker | Side | Filled qty | Average price | Fees (USD) | Status |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 2026-11-18 11:01 ET | IEF | BUY | 218 | 90.6200 | 0.99 | filled |
| 2026-11-18 12:30 ET | XLP | BUY | 40 | 91.6200 | 0.99 | filled |
| 2026-11-18 12:31 ET | ACM | BUY | 130 | 83.0490 | 0.99 | filled |
| 2026-11-20 10:33 ET | IEF | SELL | 84 | 91.4750 | 1.00 | filled |
| 2026-11-20 10:56 ET | USMV | BUY | 63 | 99.9900 | 0.99 | filled |
| 2026-11-20 10:58 ET | XLV | BUY | 22 | 179.2000 | 0.99 | filled |
| 2026-11-20 10:59 ET | GLD | BUY | 9 | 325.2470 | 0.99 | filled |
| 2026-11-20 11:00 ET | PDD | BUY | 97 | 85.7700 | 0.99 | filled |
| 2026-11-20 11:02 ET | WWD | BUY | 24 | 327.5880 | 0.99 | filled |
| 2026-11-20 11:03 ET | SPY | BUY | 42 | 705.0830 | 0.99 | filled |
| 2026-11-24 09:47 ET | NVDA | BUY | 22 | 155.5200 | 0.99 | filled |
| 2026-11-25 09:47 ET | ACM | SELL | 130 | 80.7240 | 1.01 | filled |

## Risk actions and halts

### Vetoes by reason

- cash_floor: 2
- core_target: 2
- regime: 3
- spread: 2

### Skips by reason

- Expecting ':' delimiter: line 1 column 759 (char 758): 1
- Session aborted: Broker positions snapshot failed check_broker_input validation on both attempts with 'invalid broker decimal: avgCost' although the re-fetched executor envelope contains no avgCost key (raw broker fields confirmed: cost_price/cur_price/qty/symbol/market only in snapshot subset); retry budget for the positions reply exhausted, so the watch run aborts pre-preflight with no orders.: 1
- Session aborted: Broker positions snapshot rejected by frozen validator on all 3 authorized saves (2026-11-25-watch-e3d77f968f6a): positions.json invalid broker decimal avgCost, caused by the persistent qty=0 closed ACM row (cost_price 0). Step-2 precondition (all four broker files valid) unmet, so preflight/reconcile/plan/prepare/orders were not run.: 1
- Session aborted: Step 2 broker snapshot validation exhausted: positions.json rejected on 3/3 authorized saves with 'invalid broker decimal: avgCost'. Broker reports a closed ACM row (qty 0, cost_price 0) that the frozen positions validator rejects, and executor confirms its positions tool cannot exclude zero-quantity positions. Dropping or normalizing the row would falsify a safety-critical input, and preflight requires all four broker files to validate, so this watch run ends with no preflight, no planning and no orders.: 1
- Session aborted: audit evidence retention command python3 -c: scripts/plan_session.py:12 import _common failed with ModuleNotFoundError: No module named '_common'; reconcile, grade_calls and score_hypotheses succeeded; available inputs and original agent evidence retained: 1
- Session aborted: broker positions snapshot rejected by frozen validator: broker returns a zero-quantity closed ACM row (cost_price 0) after the 2026-11-25-morning-2c22f7e3a63a full ACM sell; check_broker_input.py fails all three authorized saves with invalid broker decimal: avgCost (retries exhausted), so preflight was never entered and no orders were placed: 1
- Session aborted: convert_quotes refused twice (exit 2) on planning quotes; US.USMV source update_time ***2389 outside 60s freshness gate in both batches; retry exhausted; no orders dispatched: 1
- Session aborted: convert_quotes refused twice: plan-time quote batch (quotes-raw.json) failed the 60-second freshness gate. Retry batch update_times 16:56:30-16:56:56Z were 60-150s old at conversion; no orders were prepared or dispatched (plan/prepare never run).: 1
- Session aborted: convert_quotes.py refused after the single permitted retry: quote batch source timestamps exceeded the frozen 60-second freshness limit (oldest US.WWD update_time ***6752 = 2026-11-23T17:35:26Z vs conversion ~2026-11-23T17:38:05Z); limit not relaxed; planning never started, no tickets prepared, no orders dispatched: 1
- Session aborted: convert_quotes.py refused twice (initial batch + one retry with fresh quotes): US.USMV snapshot update_time ***8238 exceeded the 60s maxAgeSeconds limit in both batches (106s stale at second attempt), so no quotes.json could be produced; plan/prepare/orders therefore not run: 1
- Session aborted: convert_quotes.py refused twice (single retry consumed): US.ACM quote source timestamp ***3972 stale/unchanged beyond the 60s freshness gate; no plan, no tickets, no orders placed: 1
- Session aborted: finish: phase finish is not allowed after prepare for watch: 1
- Session aborted: positions broker snapshot failed validation on all 3 allowed saves: PDD cost_price reported as 85.***0001 rejected by frozen validator (invalid broker decimal: avgCost); retries exhausted, so preflight/reconcile/plan/prepare were never entered and no orders were placed: 1
- Session aborted: positions snapshot unusable pre-preflight: two independent broker fetches (15:37Z and 15:41Z) both return a closed zero-quantity ACM row (qty 0, cost_price 0) and the frozen parse_positions validator rejects avgCost 0 as 'invalid broker decimal: avgCost' (identical failure ended watch run 2026-11-25-watch-3f66e8bed14e at 15:05Z), so positions.json cannot validate and reconcile cannot run. Consequence: the persistent PortfolioState halt from morning run 2026-11-25-morning-2c22f7e3a63a (haltReason 'order history mismatch: qty', caused by a mid-flight history row for order ***7814 showing qty 70/status 2 against a 130-share ticket) stays uncleared; the broker now shows that ACM SELL fully filled 130 at avg 80.724 while state.json still carries ACM 130 and cash 11070.945 vs broker balance 22563.173. This session placed zero orders and prepared zero tickets.: 1
- Session aborted: preflight: phase preflight is not allowed after preflight for watch: 1
- Session aborted: reconcile: phase reconcile is not allowed after prepare for watch: 1
- Session aborted: reconcile: reconcile.py failed: order history mismatch: qty; no further order work: 1
- Session aborted: reconcile: reconcile.py failed: see persisted command receipt; no further order work: 1
- Session aborted: start broker inputs: python3 scripts/check_broker_input.py --kind positions --file runtime/inputs/2026-11-25-audit-a9391aaf3265/positions.json --stdin exited 2; ACM qty=0 cost_price=0 rejected as invalid broker decimal: avgCost on initial reply and both permitted fresh retries; reconciliation unavailable; unchanged replies retained in positions-replies.json: 1
- Session aborted: step 2 aborted: positions snapshot failed the frozen validator 3 of 3 authorized saves (positions.json: invalid broker decimal: avgCost) because the broker keeps reporting the closed qty=0 ACM row with cost_price 0; preflight never entered, no orders placed: 1
- Session aborted: step 2 broker baseline incomplete: check_broker_input.py rejected the positions snapshot 3/3 authorized saves with 'positions.json: invalid broker decimal: avgCost' because the broker keeps reporting the closed ACM row qty=0/cost_price=0 after the 2026-11-25 morning full exit (order ***7814); all four broker files must validate before preflight, so the run aborts with no orders: 1
- Session aborted; retained all evidence: 24
- Trusted news cutoff unavailable: completed move session 2026-11-16 has null open/close in frozen calendar: 15
- below_min_notional: 1
- bounce requires trend-or-support and RVOL < RVOL_CAP: 7
- calendar skip: audit outside its competition session window: 2
- calendar skip: morning outside its competition session window: 2
- calendar skip: watch outside its competition session window: 27
- classification does not authorize a long entry: 23
- core buy requires recorded and reconciled sell fills: 3
- drift RVOL below R_drift: 1
- fresh quote moved past the ticket limit price: 8
- fresh quote spread exceeds frozen limit: 1
- session aborted before dispatch: 6
- stale or future quote timestamp: 1
- ticket limit price no longer matches fresh quote: 4

### Halts by reason

- Audit incomplete: completed session bars unavailable; daily_report numeric metrics missing: 1
- Trusted news cutoff unavailable: completed move session 2026-11-16 has null open/close in frozen calendar: 1
- missing or invalid candidate, bars, analyst, debate or rating reply: 30
- missing or invalid required broker rows list: 1
- missing required broker field: avg_cost: 1
- missing required broker field: qty: 1
- order history mismatch: qty: 1
- state is halted: 3
- unexplained broker/book difference: 2

## Privacy

Account IDs, tokens and raw broker payloads are never included. Any number of seven or more digits, including order IDs, is masked as *** plus its last four digits.
