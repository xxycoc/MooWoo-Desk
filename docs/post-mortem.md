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
- **18 November, 20:04 UTC (15:04 New York):** a watcher halted with
  `missing required broker field: qty` after the coordinator dropped one field
  while copying an order-history row. Trading stayed halted through the close
  and audit until an operator restart on 19 November. Addendum 25 made malformed
  or missing input files abort only that run instead of setting the persistent
  halt.
- **After the restart:** the dashboard kept showing HALTED because a restart
  writes no ledger event. The public feed now carries the desk's halt state
  (`meta.desk`) so the banner reflects the runtime flag rather than the last
  recorded halt.
- **Addenda 22-25:** allocation was too small for the designed experiment,
  position field names were wrong, asynchronous valuation caused false halts,
  never-sent authorizations reserved cash, audits lacked bars, core buys could
  not follow sells, and a close watcher fired after closing. Each produced a
  code or prompt correction plus a regression test where the failure is
  deterministic.
- **Performance and hypothesis grading:** to be filled from
  `docs/results.md` and the final audit. No interim number is extrapolated.

- **19 November, 11:47 New York:** with about 66% of the account in cash, Siang Woo
  asked to invest it the same day, so the morning schedule was started by hand on
  agent version 33 (Addendum 27). It re-rated the movers, then stopped before
  planning because the 14-symbol quote batch failed the 60-second freshness check
  twice: at midday, quieter ETFs had last-update times 60 to 150 seconds old. No
  order was prepared. The 60-second limit was kept, and the next attempt is the
  scheduled 09:35 run on 20 November.

## What went right

- The model boundary held: no model-sized or discretionary order was placed, and
  order arguments came from checked tickets.
- Missing or inconsistent broker inputs halted a run instead of filling gaps with
  guesses; optional evidence such as unavailable credit counts stays null.
- The ledger, exporter and dashboard kept private account data out of public
  output, and the dashboard never became an order surface.
- **19 November:** Anthropic listed as ANT on Nasdaq. The desk did not trade it:
  ANT was outside the universe frozen on 16 November and had no price history for
  the screener. No discretionary exception was made.
- Each deterministic failure above has a regression test, so a repeat of the same
  input shape fails visibly instead of silently.

## What went wrong, and what changed

| Problem | Response | Where |
| --- | --- | --- |
| Too many agents and a long context made a daily session impractical | One researcher-rater, inline briefs, five candidates, shorter context | Addenda 13-19 (`9960049`, `92fecfa`, `016da7c`) |
| Prose-wrapped or batched model output broke ingestion | Strict JSON, one ticker per call, explicit null model provenance | Addenda 17-18 (`08a9fb6`, `8ee921d`) |
| Cloud revision drift masked local fixes | Pinned revision, prompt hashes checked in deployment | Addendum 20 (`99ba8b1`) |
| Quote age and marketability rejected valid tickets | Re-check at dispatch without altering the saved ticket | Addendum 21 (`8390191`) |
| Snapshot cash and positions came from different moments | Scaled valuation tolerance and an explicit reconciliation contract | Addenda 22-24 (`283c534`, `7053f49`, `ed612cb`) |
| Close watchers fired after the close | Close schedules run five minutes before the early and regular closes | Addendum 25 (`082123d`, `9ed01e3`) |
| A copied order-history row lost its quantity and halted the desk | Trimmed broker replies, save checks, per-run abort instead of a persistent halt | Addendum 25 (`c2d44d2`, `082123d`) |
| The dashboard kept showing HALTED after the operator restart | Feed carries the desk halt state from runtime state (`meta.desk`) | `1c1209e`, `8adffc6` |

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
