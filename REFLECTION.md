# Reflection (draft)

> Draft written 19 November 2026. This is my reflection as the desk owner, not a
> results report. Final numbers belong in the generated `docs/results.md` and the
> auditor's last report; this file should be revisited after the 27 November close.

## What surprised me

The stock-picking question was the smallest part of the work. Most of the time
went into making a scheduled, unattended paper desk fail safely: clock checks,
leases, input validation, reconciliation, stale cloud revisions and the shape of
model output. On 17 November thirteen attempts produced no orders at all, not
because the idea was disproved but because the handoffs were not yet reliable.

I also expected the multi-agent debate to be the interesting part. In practice
the extra agents added copying delay and context without a decision I could
audit, so I retired them under Addendum 19. One researcher-rater with a strict
contract was easier to test and to explain.

## What I would change

- Start from the deployed revision and one full paper session, then add agents.
  Prompt and deployment drift cost more than the first strategy iteration.
- Treat every broker input as adversarial from day one. The valuation, history
  copy and after-close watcher failures all came from assuming a clean payload.
- Design the audit and the public projection alongside the order path. The
  ledger and scrubber were more valuable than any single model prompt.
- Keep the experiment narrow. A 60-session volatility-weighted core plus a
  five-name satellite is already hard to attribute in eight sessions.

## What the agents got right or wrong

- **Right:** the analyst produced ratings that could be validated, cited and
  graded, and the executor forwarded only code-issued arguments. The boundary
  between language and order authority held.
- **Wrong:** early debate and batched formats were brittle; some runs failed on
  JSON shape or stale quotes, and the cloud once ran stale code despite updated
  prompts. These were process failures, not trading insights.
- **Still unknown:** whether the news-aware rating beats follow and fade over
  the preregistered horizons. That is what the hypothesis table and the auditor
  are for, and it is not something I should assert from memory.

## What I am not claiming

I am not claiming a repeatable edge, a calibrated confidence score, or that the
dashboard is the broker's book. The window is short, the ratios are unstable,
and any missing evidence stays missing rather than being filled with a guess.
What I do claim is a reusable, tested mechanism for running a scheduled paper
desk where code, not a model, owns sizing, risk and order tickets.
