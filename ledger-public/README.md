# Decision log (public, masked copy of the ledger)

Every decision the desk made from 17 to 27 November 2026, as recorded in its private
hash-chained ledger, published after the window as the pre-registration promised
([Addendum 33](../PREREGISTRATION.md)). Source: private ledger branch `ledger`, commit
`2a2b1e92c2ba26afe07505d1950eafe7fa776f6f` (27 Nov 2026, 21:14 UTC).

## What is here

| Folder | What it holds |
| --- | --- |
| `logs/` | 155 run logs, one per scheduled or manual run: 742 events, each linked to the previous one by SHA-256 |
| `tickets/` | The order tickets Python prepared for each run, with the config hash they were built under |
| `reports/` | The after-close audit report for each trading day |
| `hypotheses/` | The pre-registered hypothesis settings |
| `MANIFEST.json` | For each log: event count, head hash, SHA-256 of the private file, and which events were masked |

## Event types

| Type | Count | Meaning |
| --- | ---: | --- |
| `run_started` | 88 | A run began; records starting cash, equity, risk tier, and the config and prompt hashes |
| `screen` | 17 | The screener's top movers for the day |
| `rating` | 55 | The analyst's news rating for one mover: class, confidence, evidence, and what would prove it wrong |
| `risk_verdict` | 46 | The risk desk's approve, resize or veto, with the reason |
| `core_rebalance` | 25 | A planned change to the steady-fund (core) holdings |
| `order_intent` | 46 | An order Python decided to place |
| `order_submitted` | 12 | An order the executor sent to the paper account |
| `fill` | 12 | A filled order: quantity, average price, fees (the same 12 fills as [docs/results.md](../docs/results.md#trades)) |
| `outcome` | 55 | The graded result of a rating: stock return against SPY over its horizon, right or wrong |
| `halt` | 48 | A run or the desk stopped, with the reason |
| `reflection_note` | 338 | Plain-text notes written during runs, including every abort reason |

Each event carries `runId`, `seq`, `ts`, `type`, `hash` and `prevHash`. Decisions about the
same trade share a `decisionId`, so a rating, its risk verdict, the order and the fill can be
followed in order.

## Masking

Every standalone run of seven or more digits (order IDs, news-article IDs, epoch times and
random seeds) is shown as `***` plus its last four digits. `hash`, `prevHash`, `runId`,
`sourceRunId` and `decisionId` are unchanged. The logs hold no account IDs or credentials.

Masked events keep their original `hash` and `prevHash`, so:

- all 660 unmasked events still verify against their own hash;
- every `prevHash` link in every chain is intact;
- the 82 masked events (listed in `MANIFEST.json`) verify only against the private copy,
  whose file hashes are also in the manifest.

`scripts/mask_ledger.py` made this copy; it refuses to run if any private log fails
verification.

## Not included

Raw broker payloads stay private: 5,228 input snapshots (cash, positions, quotes, bars),
480 broker order receipts, 68 agent hand-off files and the runtime state file. Their effect
is recorded in the events above.
