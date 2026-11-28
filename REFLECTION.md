# Reflection

Written 28 November 2026 by Siang Woo, after the trading window closed. The numbers are in
[docs/results.md](docs/results.md); the full failure list is in
[docs/post-mortem.md](docs/post-mortem.md).

## What I set out to do

I wanted a desk where AI does what it is good at, reading the news and explaining a price
move, and code does what it is good at, following rules exactly. The test was simple: when a
stock jumps or drops, does knowing the reason help a trade?

## What worked

The split held for all eight trading days. No AI agent ever chose a stock size or placed an
order that code had not approved. When the market was weak, the rules blocked new trades.
When the broker sent something unexpected, the desk stopped rather than guessed, and the
ledger showed exactly why within minutes.

The account ended about 2% up on paper while the S&P 500 fell 1.4%, with a largest fall of
1.4%. Eight days is too short for that to mean the idea works. It does mean the risk design
kept losses small while the desk was learning.

## What failed

The first day was lost to too many agents. Bull, bear, manager and quick agents debated each
move and passed long text to each other; thirteen attempts produced no trade. Cutting to one
analyst with short, strict answers fixed it the next day.

Then the desk stopped itself five times between 18 and 25 November. Four came from broker
data that looked different from what the code expected: a renamed field, a few seconds of
price movement, a changed average cost, an order filled in two parts. One came from our own
coordinator dropping a field while copying a broker record. Each
time I found the cause, fixed it, wrote it down and restarted the desk.

The failure that hurt most was the last one. On 27 November the desk had to sell everything
before the 13:00 close. One quiet ETF's price was 106 seconds old, a 60-second check rejected
it, and all nine sells were blocked twice; the last retry started after the close. The rule
that allowed older prices on the final day had been coded into one step but not the step
before it. I had seen that same 60-second abort on earlier days and called it harmless,
because the next run always worked. On the last day there was no next run.

I told the organisers before submitting and chose not to trade after the window, so every
number in this entry comes from 17 to 27 November.

## What I would change

- Start with one agent and one full rehearsal day, and add complexity only after it works.
- Assume every broker reply can be wrong, and test with the strange replies, not just clean ones.
- Rehearse the last day on its own. It ran different rules and had only three chances.
- Treat a failure that keeps recurring as a warning, even if it has not cost anything yet.

## How I used Qoder

- **Cloud Agents:** coordinator, analyst and executor run each session; the auditor runs
  separately after the close with no order tools.
- **Schedules:** a morning run, a watcher every 30 minutes, a close watcher and an audit, plus
  early-close versions for 27 November. 158 cloud sessions used 1,748 credits.
- **Qoder IDE:** built the dashboard and 3D trading floor (hosted on Qoder Sites), the results
  script and the presentation deck.
- **Slack:** the auditor posts a short summary written by code after each close.

## What I claim

A tested, reusable way to run a scheduled paper-trading desk where code, not AI, controls the
money, with every decision on record. I do not claim a way to beat the market, and I do not
claim a clean finish.
