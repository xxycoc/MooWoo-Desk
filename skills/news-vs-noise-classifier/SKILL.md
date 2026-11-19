---
name: news-vs-noise-classifier
description: Use when researching one abnormal mover and producing or validating the active analyst's strict four-class rating contract.
---

# News versus noise classifier

## Inputs

One coordinator-supplied candidate, decision ID, ticker, trusted cutoff and prompt
version. Use `agents/analyst/system.md`, `schemas/rating.schema.json` and
`moowoo/rating_schema.py` as the contract. The analyst can use its allowlisted
read-only Moomoo news/quote tools; it cannot write files or obtain the clock.

## Procedure

1. Research only evidence published at or before the supplied cutoff. Close moves use that session's close; gap moves use its open.
2. Choose exactly one of `explained_up`, `explained_down`, `unexplained_up`, `unexplained_down`. Explain the causal evidence, not merely the price direction.
3. Return one JSON object with `decisionId`, `ticker`, `class`, `confidence`, `tier`, `reason`, `evidence`, `newsCutoff`, `expectedMove`, `wrongIf`, `model`, `promptVersion`. Use tier `single`; finite confidence must be between zero and one; reason must be nonempty and at most 600 characters.
4. Evidence items contain exactly `id`, `headline`, `source`, `publishedAt`; IDs are nonempty and unique and publication timestamps use UTC `Z`. State continuation over five sessions for explained moves or reversal over three for unexplained moves, with a concrete `wrongIf`.
5. The coordinator saves the verbatim reply to `<inputs>/replies/<decisionId>.analyst.json`, then uses `scripts/ingest_ratings.py`. Missing `model` is rejected; an explicitly null model can be resolved from the analyst configuration.
6. Skip a failed candidate with evidence of the failure; do not invent a valid rating. The coordinator bounds candidate calls to its run lease and ten-minute per-candidate deadline.

## Outputs

Validated `ratings.json` (an empty array if none pass), rating events and logged
candidate failures, consumed by `scripts/plan_session.py`. Only explained-up and
unexplained-down can become long-entry proposals in `moowoo/sizing.py`.

## Limits

No sizing, order tools or discretionary trade authority. Return raw JSON: one
complete code fence is tolerated with a warning, but prose wrappers, duplicate
keys and nonfinite numbers are rejected. Confidence is not proven calibration.
Retired debate and quick prompts are history, not extra votes in this workflow.

