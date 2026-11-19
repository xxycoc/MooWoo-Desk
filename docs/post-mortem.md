# Post-mortem (draft)

> Draft written 19 November 2026, before the 27 November early close. Final
> account results, hypothesis verdicts and credit figures must be taken from the
> completed audit and `docs/results.md`; this draft does not assert a finished
> trading result or an edge.

## What we set out to test

The Moomoo x Qoder challenge asked for a paper-trading desk with a stated
strategy and evidence trail. MooWoo Desk asked one narrow question: does a
news-aware rating of unusual US stock moves add value over simple
follow-the-move and fade-the-move rules? The preregistered hypotheses, their
horizons and the frozen universe are in [PREREGISTRATION.md](../PREREGISTRATION.md).
Only paper trading, US stocks and ETFs, long only.

## What we built

- A deterministic Python boundary for screening, core allocation, sizing, risk
  checks, dispatch authorization and reconciliation. Language models rate moves
  and forward exact code-issued paper tickets; they never size or place orders.
- A hash-chained event ledger plus a private runtime repository, with a
  field-allowlisted scrubber that feeds a read-only dashboard.
- Qoder Cloud Agents and schedules for the morning, watcher and audit sessions,
  with a separate auditor that has no order tools.
- A reusable skills index and failure-path tests, not just a happy path.

## What happened during the window

- **17 November:** thirteen attempts produced no orders and no accepted debate
  rating. Addendum 19 retired bull, bear, manager and quick in favour of one
  researcher-rater and per-order quote calls.
- **Addendum 20:** the cloud checked out stale code after prompts changed.
  Revision and prompt-hash alignment became part of the deployment contract.
- **Addendum 21:** a small fresh-quote move rejected an otherwise marketable
  limit. Dispatch now checks marketability without changing price or identity.
- **Addenda 22-25:** allocation was too small for the designed experiment,
  position field names were wrong, asynchronous valuation caused false halts,
  never-sent authorizations reserved cash, a copied history row lost quantity,
  audits lacked bars, core buys could not follow sells, and a close watcher
  fired after closing. Each produced a code or prompt correction plus a
  regression test where the failure is deterministic.
- **Performance and hypothesis grading:** to be filled from
  `docs/results.md` and the final audit. No interim number is extrapolated.

## What went right

- The model boundary held: no model-sized or discretionary order was placed, and
  order arguments came from checked tickets.
- Missing or inconsistent broker inputs halted a run instead of filling gaps with
  guesses; optional evidence such as unavailable credit counts stays null.
- The ledger, exporter and dashboard kept private account data out of public
  output, and the dashboard never became an order surface.
- Every documented failure above has a matching contract test, so a repeat of the
  same input shape fails visibly instead of silently.

## What went wrong, and what changed

| Problem | Response |
| --- | --- |
| Too many agents and a long context made a daily session impractical | One researcher-rater, inline briefs, five candidates, shorter context |
| Prose-wrapped or batched model output broke ingestion | Strict JSON, one ticker per call, explicit null model provenance |
| Cloud revision drift masked local fixes | Pinned revision, prompt hashes checked in deployment |
| Quote age and marketability rejected valid tickets | Re-check at dispatch without altering the saved ticket |
| Snapshot cash and positions came from different moments | Scaled valuation tolerance and an explicit reconciliation contract |
| Close watchers fired after the close | Close schedules run five minutes before the early and regular closes |

## Limits

- The experiment is about eight sessions. Annualised ratios are unstable and
  descriptive only; they are not evidence of a durable edge.
- Grading needs matured outcomes. Unmatched or ungraded calls are reported as
  unavailable, never as zero.
- Paper fills, modelled fees and delayed marks are not a broker statement.
- The auditor's observations and the final report are separate from this draft;
  where the two disagree, the ledger and the audit take precedence.

## Open items before submission

- [ ] Run `.venv/Scripts/python.exe scripts/build_results.py --ledger <private-ledger> --out docs/` on the final ledger and review the generated files.
- [ ] Complete the final audit: verified fills, drawdown, credits and Brier score.
- [ ] Confirm the deployed revision and prompt hash match the pushed source.
- [ ] Fill the performance and hypothesis placeholders above from that output.
