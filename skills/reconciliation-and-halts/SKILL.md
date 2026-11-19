---
name: reconciliation-and-halts
description: Use when reconciling cumulative broker fills, resolving reserved tickets or investigating a persistent account/book halt.
---

# Reconciliation and halts

## Inputs

Validated complete order history, positions, cash, ticket manifests, private event
logs and `PortfolioState`. Implementation: `scripts/reconcile.py`,
`moowoo/execution.py`, `moowoo/broker.py` and `moowoo/portfolio.py`.

## Procedure

1. Reconcile a baseline before planning and reconcile again after recording orders. Use the owned phase runner, including its mid-batch reconciliation path for dependent core buys.
2. Apply only the increment beyond each order's recorded cumulative fill checkpoint. Keep repeated snapshots idempotent and pending commitments reserved.
3. Compare parsed broker books against local holdings. Quantity mismatches remain real failures; position-value comparisons use the implemented tolerance, the larger of $1 and 0.25% of marked value, for asynchronous snapshots.
4. For a prepared but never-sent authorization, require complete history proving no matching order, plus explicit no-handoff evidence or a quote deadline more than fifteen minutes old. Use the existing expired-authorization path; never manually free cash.
5. Record releases without making the decision reusable. An uncertain send is not automatically an absent order.
6. Preserve persistent halts for actual broker/book disagreements. A malformed input file aborts one run instead; correct inputs before retrying. Any authorized restart must retain its explanation and evidence.

## Outputs

Reconciled state, fill deltas, updated reservations, release/checkpoint events and
halt evidence. Dependent actions see actual fills, not planned or accepted orders.

## Limits

Do not silently rewrite history, ignore unmatched orders, equate cash with
buying power, or assume every comparison uses exact equality. Complete history
and lease ownership remain necessary. Do not clear a true halt merely to resume
trading or re-dispatch a released decision.

