---
name: price-action-setup
description: Use when calculating reproducible price-action context for a screened candidate without changing its position size.
---

# Price-action setup

## Inputs

Completed daily OHLCV bars through the trusted as-of date, side `long`, and
parameters in `moowoo/config.py`. Implementation: `moowoo/setup_score.py` and
`moowoo/indicators.py`.

## Procedure

1. Trim bars with `moowoo/screener.py::through_asof` before computing context. Never pass later candles into an earlier decision.
2. Call `setup_score(frame, side="long")`; use `swing_indices`, `support_levels` and `candle_patterns` rather than subjective redraws.
3. Confirm swing points with two bars on either side. Unconfirmed recent extrema are not confirmed pivots.
4. Inspect the score's five components: trend, nearby support/resistance, descending trendline break, candle pattern and volume. A direct call returns `total`, `points`, `asof` and `side`.
5. Follow `scripts/gather_inputs.py`, which stores only the total as `setupScore` in `candidates.json`; rating ingestion logs that scalar. Keep sizing in `moowoo/sizing.py` and limits in `moowoo/risk.py`.

## Outputs

A zero-to-five setup score, added to candidate evidence by the input gatherer,
not by the screener itself. Detailed points are not automatically logged by that
path. Support levels can separately participate in the
explicit bounce eligibility and stop calculations in `propose_entry`.

## Limits

`SETUP_SCORE_USE` is `log_only`: no score-based size, ranking override or new risk
rule. Distinguish the diagnostic score from the existing support-based entry
rules. The historical setup buckets did not demonstrate a monotonic edge.
