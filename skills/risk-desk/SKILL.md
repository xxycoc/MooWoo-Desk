---
name: risk-desk
description: Use when evaluating a deterministic trade proposal against account, market and registered portfolio risk limits.
---

# Risk desk

## Inputs

A whole-share proposal from `moowoo/core.py` or `moowoo/sizing.py`, reconciled
`PortfolioState`, fresh quotes, prices, completed bars, current time and the
applicable calendar. Read `moowoo/risk.py`, `moowoo/portfolio.py`,
`moowoo/config.py` and the latest registered rule changes.

## Procedure

1. Call `risk.check(proposal, state, market)` through `scripts/plan_session.py`; do not replace it with an LLM verdict.
2. Preserve its ordered checks: halt/kill and exits-only tiers, daily loss, final day, first minutes, regime, duplicate decision, order count, price age, spread, correlation, bounce count, satellite invalidation, concentration, sleeve/cash/liquidity limits and core budget.
3. Respect current entry limits: 1.5% daily loss, drawdown tiers at 2/4/6%, 30 session orders, quotes at most 60 seconds old, spread at most 0.5%, correlation at most 0.80 and order notional at most 0.5% of 20-session average dollar volume.
4. Count pending commitments, not just filled positions. Apply whole-share resizing and the minimum $2,000 buy after limits.
5. Keep all checks and the first fired rule. Missing safety inputs fail closed; never synthesize values to obtain approval.
6. Pass approved tickets through prepare and the separate per-ticket dispatch check. Risk approval alone is not authority to call a broker.

## Outputs

`verdict` (approve/resize/veto), `qtyAfter`, `firedRule`, and per-rule `checks`,
recorded with the resulting plan/tickets and event evidence.

## Limits

Sells bypass entry-only gates, not duplicate decisions or unreserved-long-share
limits. Calendar and dispatch checks still apply. Scheduled protective exits are
not guaranteed stop fills. Never change frozen/default limits outside a dated,
explicitly authorized rule-change workflow.
