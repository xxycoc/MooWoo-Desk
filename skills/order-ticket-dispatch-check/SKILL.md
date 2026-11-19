---
name: order-ticket-dispatch-check
description: Use immediately before handing one prepared paper-order ticket to the executor, or when a fresh quote invalidates authorization.
---

# Order ticket dispatch check

## Inputs

An approved manifest from `scripts/plan_session.py` or `scripts/watch.py`, an owned
run lease, persisted prepared attempt, reconciled state and a fresh single-symbol
quote. Read `scripts/dispatch_check.py`, `scripts/execute_tickets.py`,
`moowoo/execution.py` and `agents/executor/system.md`.

## Procedure

1. Use the coordinator phase runner to preflight and prepare the manifest; persist attempts before any broker handoff.
2. For each ticket, obtain a fresh quote through the analyst, save/validate it and run `scripts/dispatch_check.py` using the exact arguments in the current coordinator prompt.
3. Require owned remote lease, valid paper-account binding, current market window, unused prepared attempt and the quote-age/spread checks applicable to the order.
4. Keep the saved limit unchanged. For a buy, the fresh required price cannot exceed that limit; for a sell it cannot fall below it. A fresh quote need not exactly equal the original quote.
5. For conditional core buys, require all planned core sells fully filled/reconciled and actual core/cash budgets passing. Projected proceeds alone are insufficient.
6. Only `ok:true` permits handing the exact returned arguments privately to the executor, within the quote deadline. Rechecks follow the durable checkpoint. An age-only `retryable:true` permits one quote refresh, not an order retry.
7. Save the broker reply immediately and record it through the phase runner; reconcile before any dependent action or uncertainty recovery.

## Outputs

One bounded dispatch authorization or a logged skip/failure, then submission and
fill evidence when actually returned/reconciled. Raw authorization arguments are
private and must not enter public documentation or feeds.

## Limits

No discretionary price/quantity changes, replay of a decision, or blind retry
after an ambiguous broker response. Broker acceptance is not a fill. Source
permissions default to human approval; unattended paper execution requires the
separately logged and configured autonomy override.
