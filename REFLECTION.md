# Reflection (draft)

> DRAFT written 19 November 2026. This is my reflection as the desk owner, not a
> results report. Final numbers belong in the generated `docs/results.md` and the
> auditor's last report; this file should be revisited after the 27 November close.

## What worked

The deterministic Python boundary held. Language models researched moves and
returned structured ratings; they did not size positions, choose quantities or
place discretionary orders. Code screened candidates, applied risk limits, issued
tickets and required a dispatch check before the executor forwarded exact paper
arguments. That separation made failures visible and testable.

The evidence trail also worked. Every decision and reconciliation step appended
to a hash-chained ledger; the public dashboard was built from a field-allowlisted,
scrubbed projection rather than the private runtime. Missing or inconsistent
broker inputs stopped a run instead of being filled with guesses, and optional
evidence such as unavailable credit counts stayed null. The separate auditor,
with no order tools, graded calls and reported gaps after the close.

## What failed and why

The desk spent its first day failing at handoffs, not at trading. On 17 November
thirteen attempts produced no orders and no accepted debate rating: too many
agents, too much copied context, prose-wrapped or batched model output, and quote
delay. The cloud also checked out stale code after prompts changed, so local
fixes were not what ran. Addenda 17-20 replaced the debate path with one
researcher-rater, enforced strict JSON and aligned the deployed revision with the
recorded prompt hash.

On 18 November a watcher halted at 15:04 New York with
`missing required broker field: qty` because the coordinator dropped a field while
copying an order-history row. The halt persisted, so later runs and the close
audit refused to start until an operator restart. Addendum 25 made malformed or
missing inputs abort one run instead of halting the desk.

The public dashboard then stayed on HALTED after that restart, because a restart
writes no ledger event. The feed now carries the desk's halt state from the
runtime state file (`meta.desk`), so the banner reflects the current flag rather
than the last recorded halt.

## What I would change

- Start from the deployed revision and one full paper session, then add agents.
  Prompt and deployment drift cost more than the first strategy iteration.
- Treat every broker input as adversarial from day one. The valuation, history
  copy and after-close watcher failures all came from assuming a clean payload.
- Design the audit and the public projection alongside the order path. The
  ledger and scrubber were more valuable than any single model prompt.
- Keep the experiment narrow. A volatility-weighted core plus a five-name
  satellite is already hard to attribute in eight sessions.

## How Qoder and Cloud Agents were used

- **Cloud Agents:** three active trading agents (coordinator, analyst and
  executor) plus a separate auditor with no order tools. The coordinator owns the
  clock, files and session phases; the analyst rates one candidate or returns a
  requested quote; the executor returns private broker snapshots and forwards
  exact code-authorized paper tickets. The auditor reconciles, grades and reports
  after the close.
- **Schedules:** six cron schedules in `America/New_York`: morning at 09:35, a
  regular watcher every 30 minutes from 10:00 to 15:30, a close watcher at 15:55,
  an audit at 16:10, and early-close variants on 27 November at 12:55 and 13:10.
- **Slack:** each audit close summary is written in code (`scripts/audit_report.py`)
  and posted by the audit schedule sink; only the auditor, which has no order
  tools, is connected to Slack.
- **Dashboard and floor:** the read-only dashboard and its 3D trading floor were
  built in Qoder and published on Qoder Sites. The floor is a visualization of
  the scrubbed feed, not an order surface.
- **Results:** `scripts/build_results.py` was written in Qoder to turn the private
  ledger into submission metrics without exposing account data.
- **Credits:** usage is measured per session in [docs/qoder-usage.md](docs/qoder-usage.md);
  a value that was not measured remains unavailable rather than zero.

## What I am not claiming

I am not claiming a repeatable edge, a calibrated confidence score, or that the
dashboard is the broker's book. The window is short, the ratios are unstable,
and any missing evidence stays missing rather than being filled with a guess.
What I do claim is a reusable, tested mechanism for running a scheduled paper
desk where code, not a model, owns sizing, risk and order tickets.
