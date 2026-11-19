---
name: core-satellite-allocator
description: Use when proposing the five-ETF core rebalance or confidence-scaled satellite entries under registered allocation limits.
---

# Core-satellite allocator

## Inputs

Reconciled `moowoo/portfolio.py::PortfolioState`, pending tickets, current prices
and quotes, aligned ETF bars, validated ratings and candidate bars. Read
`moowoo/core.py`, `moowoo/sizing.py`, `moowoo/config.py` and SIZING-01 in
`config/rule-ledger.jsonl` before proposing changes.

## Procedure

1. `core.weights` calculates inverse-volatility targets from 60 aligned daily returns (61 closes) for USMV, XLP, XLV, IEF and GLD, totaling 30%.
2. `core.propose_core` proposes whole-share changes at a relative target deviation of at least 25%. It orders sells before buys and respects reserved sell quantities.
3. Use `core.projected_core_state` only to size conditional core buys. Never persist projected cash or positions as actual holdings.
4. `sizing.propose_entry` maps explained-up to drift and unexplained-down to bounce. Notional starts at 20% equity times confidence times `min(1, .02 / daily_sd)`, halved in the reduced tier, then floored to whole shares. Enforce setup eligibility and $2,000 minimum buys.
5. Route every proposal through `moowoo/risk.py::check`. Account for existing/pending exposure, 60% satellite cap, 10% cash floor and stricter regime limits.
6. Before a core buy, `core.require_core_fills` checks actual cash and core budgets including all reserved buys and fees. CORE-REBALANCE-02 permits cash-funded buys within the cash floor and core limit; otherwise every planned core sell must be fully recorded and reconciled. Unfilled proceeds never fund buys.

## Outputs

Proposals and sizing evidence, followed by the approved ticket manifest from
`scripts/plan_session.py`. This is not an order receipt or a fill.

## Limits

SIZING-01 explicitly loosens the original allocation/spread rules; retain the
original freeze and disclose the deviation. Normal and step-up caps are both
60%. The historical quick multiplier remains in code but does not describe the
active `single` analyst. No model-selected quantities or leverage.
