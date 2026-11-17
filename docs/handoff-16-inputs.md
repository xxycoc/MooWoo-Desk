# Deterministic morning and watch inputs

Run from the pinned source checkout. `gather_inputs.py` runs only after a
successful baseline reconciliation. It reads the runner's `.session.json` and
`state.json`; it does not initialize balances, call the broker or place orders.
Use the exact `inputs` directory returned by `start`. Commands below use
`<inputs>` as that placeholder. Never pass `--now` in a live session.

## Coordinator commands

After the existing `start`, broker snapshots, `preflight` and `reconcile`:

```sh
python3 scripts/gather_inputs.py --kind morning --inputs <inputs>
```

For watch, use this instead:

```sh
python3 scripts/gather_inputs.py --kind watch --inputs <inputs>
```

Morning debates/ingestion use `candidates.json`, in its given order. Keep writing
only validated primary ratings to `ratings.json` through the existing workflow;
no ratings are fabricated by gathering. If no candidates exist, use `[]`.
`quickSecondOpinionRequired` describes a separate quick call, never the primary
rating's `secondOpinion` flag.

Immediately before plan, ask analyst to perform the read-only request in
`quote-request.json`. Save the exact JSON reply to `<inputs>/quotes-raw.json`;
multiple batch replies form a JSON array. Then run:

```sh
python3 scripts/convert_quotes.py --inputs <inputs>
python3 scripts/run_session.py --kind morning --phase plan
python3 scripts/run_session.py --kind morning --phase prepare
```

Use `--kind watch` for the last two commands in watch sessions. If the request's
`codes` list is empty, no analyst call or raw file is needed; conversion writes
an empty, timestamped quote snapshot. Check every command's result before the
next command. The normal runner still checks remote ownership, freshness and
durable checkpoints. These scripts do not authorize dispatch.

## Output and source contracts

| File | Contents |
| --- | --- |
| `session.json` | Current session facts, run identity, and `barsAsOf` from `calendar.previous_session` |
| `bars.json` | Ticker to chronological OHLCV records with timezone-free `date`; no current-session rows |
| `gather-report.json` | Requested symbols and explicit invalid/missing/stale bar errors |
| `screen.json` | Morning only: existing deterministic screener result; also appended to this run's event log |
| `candidates.json` | Morning only: picked order, move metrics, decision IDs, cutoff, setup score, prompt hash and debate routing |
| `quote-request.json` | Analyst tool, deduplicated US codes, required fields and maximum age |
| `quotes.json` | Converter output: aware UTC `now`, `sessionDate`, `runId`, numeric last/bid/ask and source timestamp per ticker |

Bars use the existing `moowoo.data.get_daily_bars` adapter, its split-only price
adjustment, cache and 180-calendar-day history. Morning fetches the frozen
universe, positions, pending-ticket symbols, all five core ETFs and SPY. Missing
portfolio/benchmark bars halt; unavailable universe members remain screener
skips. Watch fetches held/pending symbols only: `watch.py` has no benchmark,
regime or entry calculations. Gather refuses a second completed gather for the
same run. Refresh quotes separately; never reuse quotes after a failed refresh.

Candidate news cutoffs come from the move session's frozen open/close, not the
clock at collection. Gap cutoffs use the open even though daily screening uses
full-day volume. The screen event belongs to the actual trading run and retains
its separate `asof`; no extra `scripts/screen.py` call is needed.

### Why Moomoo snapshots for quotes

The analyst already has `quote_market_snapshot` permission. The coordinator has
no quote-tool permission. Use analyst's MCP call, not shell HTTP or alternate
credentials. Yahoo daily bars are suitable for completed indicators but cannot
establish a fresh broker bid/ask spread for the frozen 60-second rule.

Moomoo's [market snapshot documentation](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-market-snapshot.html)
lists `code`, `last_price`, `bid_price`, `ask_price` and `update_time`; US snapshot
wall times are Eastern time. A basic stock quote is not the chosen source since
the spread check needs bid and ask. The generated request contains the exact
symbol list, not guessed MCP argument names: analyst must use the tool's exposed
schema. Morning requests core ETFs, held symbols and picked movers; watch
requests held symbols. Benchmarks and unpicked universe members need no quotes.

The converter accepts successful `{ret_code: 0, ret_msg: "...", data: [...]}`
envelopes, or rows under `data.quotes` or `data.snapshots`. It also accepts MCP
`content` arrays containing JSON text blocks, and an array of batch envelopes.
Rows must include a `US.`-prefixed `code` and positive finite prices (numeric
strings are accepted). It accepts snapshot `update_time` in documented
`YYYY-MM-DD HH:MM:SS` Eastern format or an ISO timestamp with an explicit offset.
It also supports exchange-local `data_date`/`data_time` pairs. The converter
never replaces source timestamps with retrieval time. Duplicate, extra,
missing, future, stale, crossed or invalid quotes fail closed. It removes an old
`quotes.json` before validating a refresh.

Example synthetic snapshot row, inside one of the above envelopes:

```json
{"code":"US.AAPL","last_price":"100.00","bid_price":"99.99","ask_price":"100.01","update_time":"2026-11-18 10:00:00"}
```

The deployed MCP JSON wrapper has not been sampled by this implementation.
Public API field documentation and offline fixtures establish the supported
mapping, not live MCP compatibility. Preserve and report an unsupported response
instead of rewriting it or inferring missing fields.

## Exact prompt replacements

These are replacement text only. No prompt or embedded agent JSON was edited.
Steps 3 onward retain their current stop, execution and cleanup rules.

### Morning steps 1–2

```text
1. Run `python3 scripts/run_session.py --kind morning --phase start` to restore
   and acquire ownership. Use its exact runId, inputs, state, log and expiresAt.
   On success, obtain exact executor account-list, complete history, positions
   and cash responses; write accounts.json, history.json, positions.json,
   cash.json and, if paginated, history-pages.json under the returned inputs
   directory before preflight. Preserve the raw JSON envelopes and transcripts.
   Never invent initial state or balances.
2. Run `python3 scripts/run_session.py --kind morning --phase preflight`, then
   `python3 scripts/run_session.py --kind morning --phase reconcile`, checking
   stop conditions after each. Only after both succeed, run
   `python3 scripts/gather_inputs.py --kind morning --inputs <inputs>`, replacing
   <inputs> with start's returned input directory. Do not supply --now. This
   command replaces the earlier standalone screen.py instructions: do not run
   a second screen or hand-assemble bars.json/session.json. Read screen.json
   and candidates.json; keep the picked order and use the supplied decisionId,
   newsCutoff, setupScore and promptVersion in the existing debate and ingestion
   workflow. Top-five independent quick calls remain second opinions only.
   Write only validated primary ratings to ratings.json; use [] for no picks.
   After debates, immediately before plan, delegate quote-request.json to
   analyst. Ask it to use quote_market_snapshot for exactly its codes and return
   the unmodified raw JSON response, including prices and source update times.
   Save the response as quotes-raw.json, or a JSON array for multiple batches.
   If codes is empty, skip the tool call. Run
   `python3 scripts/convert_quotes.py --inputs <inputs>` without --now, then
   proceed immediately to step 3. Never invent bid/ask or timestamp fields;
   never research the prior session or substitute Yahoo quotes. Preserve all
   transcripts. Any nonzero result, skipped phase or expired lease stops work
   and follows step 7; never continue with stale files.
```

### Watch step 2

```text
2. Run `python3 scripts/run_session.py --kind watch --phase preflight`, then
   `python3 scripts/run_session.py --kind watch --phase reconcile`, checking
   stop conditions after each. Only after both succeed, run
   `python3 scripts/gather_inputs.py --kind watch --inputs <inputs>`, using
   start's exact input directory and no --now override. This writes completed
   portfolio bars, session.json and quote-request.json. Do not screen, debate,
   classify or write ratings.json. Delegate quote-request.json to analyst for
   quote_market_snapshot on exactly its codes; preserve the unmodified raw JSON
   response as quotes-raw.json, or a JSON array for multiple batches. If codes
   is empty, skip the tool call. Run
   `python3 scripts/convert_quotes.py --inputs <inputs>` without --now and
   proceed immediately to step 3. Never hand-assemble market inputs, research
   the previous session or invent missing prices/timestamps. Any nonzero
   result, skipped phase or expired lease stops work and follows step 7.
```

## Rehearsal and remaining limits

Run `.venv/Scripts/python -m pytest tests/test_gather_inputs.py -q` locally.
The no-order rehearsal fixes the clock at 2026-11-18 10:00 Eastern and uses real
local bare Git repositories. It drives start, actual preflight, actual baseline
reconciliation, gathering, quote conversion, actual plan and actual prepare.
Broker fixtures include wrapped accounts/positions/orders and string cash
values. Only the yfinance provider and the gather test's small universe are
stubbed; the runner's preflight still verifies the real frozen configuration
and registered prompts. Prepared orders are never dispatched. Morning is
expected to produce core tickets; an empty watch produces a clean empty batch.

Windows validation on 2026-11-17: the initial full-suite attempt hit Application
Control while importing NumPy 2.5.5. The clone's venv was then installed with
NumPy 2.5.2 and pandas 3.0.5, both within `pyproject.toml` constraints; `pip check`
passed. File-by-file runs passed all 345 tests outside `test_runtime.py` and the
new input test file. The 22 input/phase-contract tests passed separately with
`-k 'not rehearsal'`. Those include real preflight, reconcile, plan and prepare
CLIs, with valid morning core tickets and an empty watch batch, but no Git
transport. The full new rehearsal and `test_runtime.py` each exceeded a
180-second file timeout in local Git transport. Stack captures placed the new
rehearsal inside the runner's start checkpoint push, before gathering. A second
attempt capturing Git output to files also stalled. Full durable end-to-end
success is therefore unverified on this machine. Detailed local logs are under
`.cache/test-results/` and are not committed.

The 23 runtime tests independent of Git transport also passed separately. Total
completed coverage is **390 passed** (345 existing non-runtime + 22 input/phase
contracts + 23 runtime checks). The remaining 21 existing runtime tests and two
full rehearsals are not counted as verified.

Open risks:

- No live Qoder, Moomoo or Yahoo round trip is claimed. Snapshot entitlements,
  actual wrapper/field names and provider latency remain deployment checks.
- The full universe contains 727 names. The existing adapter fetches each name
  sequentially; a cold cache or provider failures can consume the 45-minute
  lease. Finish/abort under the runner rules; do not extend or bypass the lease.
- The existing calendar lists 2026-11-14 as a completed Friday, but that date is
  Saturday, and omits Monday November 16. Thus `previous_session` for November
  17 returns November 14. This task preserves the requested calendar function
  and frozen rules; missing bars/hours fail closed. November 18 correctly uses
  November 17. This pre-existing calendar defect needs separate correction.
- The prompt introduction also says 09:35 New York is before the open. That
  sentence is inconsistent with its own schedule. The replacement numbered
  steps use the frozen runtime calendar; this task leaves prompt files intact.
- Debate/ingestion remains agent work. Quotes must be collected after it, then
  plan and prepare must finish inside the existing 60-second freshness limit.
