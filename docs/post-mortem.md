# Post-mortem

Written 28 November 2026, after the trading window closed. Numbers come from
[results.md](results.md), which is built from the private ledger by
`scripts/build_results.py`. Rule changes are in [PREREGISTRATION.md](../PREREGISTRATION.md).

## The short version

MooWoo Desk traded a USD 100,000 paper account on a schedule from 17 to 27 November 2026.
AI agents read the news about unusual stock moves; Python code decided what to buy, how much,
and when to sell.

| | Result |
| --- | --- |
| Account value at the 27 Nov close | USD 101,942 broker total (+1.94%); USD 101,981 marked at session closes (+1.98%) |
| S&P 500 (SPY), 17 Nov open to 27 Nov close | −1.36% |
| Sharpe ratio, daily closes | 3.44 (eight sessions; unstable) |
| Largest fall from a peak | −1.44% (20 Nov) |
| Realised | about −USD 242 (ACM −302, IEF part-sale +72, fees −12) |
| Unrealised, nine holdings never sold | about +USD 2,185 |
| News-rating hit rate (H1) | 52% of 50 graded calls; can't tell yet |
| Confidence calibration (H3) | Brier 0.290; target below 0.25 not met |

The desk failed its last job: it did not sell everything before the 27 November close.
That failure is explained in full below.

## What we set out to test

When a stock moves unusually, does a news-aware rating of that move help a paper trade, compared
with simply following or fading the move? The rules, hypotheses and stock universe were frozen on
16 November, before the first trade.

## What we built

- Python screens daily moves, sizes positions, applies risk limits, approves each order and
  reconciles every fill against the broker.
- Three Qoder Cloud Agents run the day: a coordinator (timetable and files), an analyst (news
  ratings and quotes) and an executor (forwards only code-approved paper orders). A fourth agent,
  the auditor, checks the books after the close and has no order tools.
- Six Qoder schedules: a morning run, a watcher every 30 minutes, a close watcher and an audit.
- A hash-chained ledger records every decision, veto, order and fill. A scrubbed copy feeds the
  public dashboard and its 3D trading floor.

## What worked

- **No AI agent ever sized or invented an order.** Every one of the 12 trades came from a
  code-issued ticket.
- **The risk rules said no when they should.** The weak-market rule blocked Disney and Target on
  19 November and a PDD bounce on 23 November. Cash-floor, spread and core-target checks vetoed
  six more tickets.
- **The money split held up.** SPY was down 1.36% over the window; the account, mostly in core
  ETFs and SPY bought after the 20 November dip, ended up about 2% on paper.
- **When unsure, the desk stopped instead of guessing.** It never made a wrong trade from a bad
  broker reply. Every stop left evidence that made the cause easy to find.

## What failed, in order

| Date | What happened | What changed |
| --- | --- | --- |
| 17 Nov | Thirteen attempts, no trades. Several debating agents passed long text around and answered in prose. | One analyst, strict short JSON answers (Addenda 17-19). |
| 18 Nov | The broker named a price field differently from what we expected. Desk stopped. | Field names fixed (Addendum 22). |
| 18 Nov | Cash and holdings were read seconds apart; prices moved; totals were USD 9.75 apart. Desk stopped. | Tolerance scaled with holdings (Addendum 23). |
| 18 Nov | The coordinator dropped a field while copying a broker record. Desk stopped. | Trimmed broker replies, save-time checks, one-run abort instead of a desk-wide halt (Addendum 25). |
| 20 Nov | After a part-sale the broker's average cost differed from ours. Desk stopped. | Book follows the broker's cost (Addendum 30). |
| 25 Nov | A sell order filled in two parts and looked like a mismatch; then a closed zero-share row failed validation. Every later run that day stopped. | Part-filled orders wait; closed rows are dropped (Addendum 31). Worked live on 27 Nov. |
| **27 Nov** | **The final sell-off never ran. Nine holdings stayed open at the close.** | **None; the window had closed (Addendum 32).** |

Each of the five stops from 18 to 25 November needed a person to restart the desk after the fix was deployed.
No stop caused a wrong trade.

## The final day

The organisers counted only realised results and asked for every position to be closed by the
13:00 New York early close on 27 November. Addendum 28 told the desk to sell everything from
12:00, with retries at 12:30 and 12:55, and to accept exit quotes up to 300 seconds old because
quiet ETFs update slowly.

What happened:

1. **12:00.** The watcher collected quotes for all nine holdings before planning. USMV's quote
   was more than 60 seconds old. The quote step rejected the whole batch, retried once, and the
   run aborted. No sell order was prepared.
2. **12:30.** Same failure; USMV's quote was 106 seconds old.
3. **12:55.** Qoder started the run at 12:57. By the time it checked the market calendar it was
   13:00:25, after the close, so it skipped.
4. **13:10.** The auditor reconciled the account with no difference and flagged that the final
   sell-off had not happened. It has no order tools and placed nothing.

**Why.** The 300-second limit was written into the per-order check only. The earlier step that
collects planning quotes kept its general 60-second limit, with no final-day exception. One slow
quote on one quiet ETF therefore blocked all nine sells. This 60-second abort had happened on
earlier days, and we treated it as harmless because the next watcher simply ran. On the last day
there were only three chances, and no test covered the final-day planning path.

**What we decided.** We told the organisers before submitting. They said anything done after the
competition date was our decision. We chose not to trade after 27 November, so every number in
this report comes from the window and every trade on record was approved by the desk's code.
The schedules were paused on 28 November.

## What we would do differently

1. **Start with one agent and one full day, then add more.** The first day was lost to too many
   agents talking to each other.
2. **Treat every broker reply as possibly wrong.** Most of these failures came from broker or quote
   data that looked different from what the code expected.
3. **Test the last day on its own.** It had a different rule set and only three chances. A
   rehearsal with a stale quote would have found the gap.
4. **Treat a repeated harmless failure as a warning.** The quote abort was a known pattern before
   it cost the final sell-off.
5. **Build the audit trail first.** The ledger made every failure above traceable within hours.

## Limits

- Eight sessions is far too short to show an edge. The annualised ratios are descriptive only.
- H2 (news rating versus follow and fade rules) could not be scored: the matched records were
  missing.
- Paper fills, modelled fees and delayed quotes are not a broker statement.
