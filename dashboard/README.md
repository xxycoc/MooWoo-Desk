# MooWoo Desk dashboard — Stage 2b

Static operations screen for the paper-trading desk. It reads a scrubbed snapshot
of the real paper ledger and rebuilds figures from the event stream. There are no API
keys or broker connections. An optional public feed updates the data without republishing the site.

## Run

```bash
cd dashboard
npm install
npm run dev
```

Open <http://127.0.0.1:5173/>. Production build:

```bash
npm run build   # tsc --noEmit && vite build, output in dashboard/dist
npm run preview
```

## Export and publish the real ledger

From the repository root, using the existing local ledger clone (no fetch or checkout):

```powershell
.venv/Scripts/python scripts/export_dashboard.py --ledger-repo C:\Users\Woo\MooWoo-Ledger-seed --ref refs/remotes/live/ledger --out dashboard/public/data
# Optional inclusive delay cutoff: --until 2026-11-18T16:00:00Z
cd dashboard
npm install # only needed when node_modules is absent
npm run check:data
npm run build
```

Publish **`C:\Users\Woo\MooWoo-Desk-18\dashboard\dist\`**, including its
`index.html`, `assets/` and `data/`, through Qoder Sites. Select this generated
folder, not the repository, `dashboard/`, or `public/`. This task does not publish
it. The relative Vite base supports static hosting; no server or browser secrets
are required. Without a remote feed, re-export, rebuild and republish to update the snapshot. `check:data`
asserts the complete Nov 17–18 snapshot; a deliberately earlier `--until` export
will not satisfy its latest-position assertions.

Everything in `dist/` becomes public and downloadable: app assets, the manifest,
and scrubbed event rows, including timestamps, decision links, tickers, prices,
quantities, cash/equity, ratings, reasons, evidence headlines, risk checks, halts
and execution notes. Logs are ordered by first event; the loader merges overlapping
runs by timestamp. Only dated morning/watch/audit run files are copied; lock files,
standalone screen artifacts, state.json, tickets, receipts and handoffs are excluded.

The exporter uses event-field allowlists and recursive removal of account,
credential, token, raw payload, hash and private-reference fields. It redacts
credential-shaped text, `/data` paths, URL query/fragment strings and runs of seven
or more digits. Broker order IDs become stable 16-letter SHA-256 aliases. Decision
IDs are retained except long numeric substrings, which receive stable aliases
consistently with their run IDs. Numbers use at most six decimal places; numeric
values of magnitude one million or more become null. Original hashes are removed,
not rebuilt: **Scrubbed export** means the original chain is **not verified**.
The output directory must be dedicated to this export; stale JSONL files are
removed so Vite cannot accidentally publish old or fictional files. The original
fixture logs remain in `fixtures/`. `--include-fixtures` explicitly adds them for
demonstration and labels the resulting combined totals as unsuitable for real-ledger use.

## Publish once with an updating feed

Create a **public** GitHub repository dedicated to scrubbed dashboard data, for
example `xxycoc/MooWoo-Desk-feed`. It may be empty; the publisher creates `main`.
Use a fine-grained GitHub token limited to that repository with **Contents: read
and write** (Metadata read is implicit). Keep the private ledger token separate.

In the deployment `.env`, set `GITHUB_FEED_TOKEN` and `FEED_REPO_URL`, for example
`FEED_REPO_URL=https://github.com/xxycoc/MooWoo-Desk-feed`. The URL may instead go
in deployment settings JSON; the token must stay in `.env`. Apply the updated
coordinator/auditor templates and schedules with `scripts/qca_deploy.py` after
the implementation is merged and the deployment revision is pinned. It passes
both values to sessions; dry runs never read or print secrets. Missing feed
configuration disables publication without affecting trading.

Build the site with the **public raw data directory URL**, including `data/`:

```powershell
$env:VITE_FEED_URL = 'https://raw.githubusercontent.com/xxycoc/MooWoo-Desk-feed/main/data/'
cd dashboard
npm run build
```

Publish `dashboard/dist/` to Qoder Sites **once**. Keep the bundled `data/` in
the site as the offline fallback. No token belongs in Vite variables or the
browser. With `VITE_FEED_URL` configured, the dashboard fetches the index and
its JSONL files with cache-busting queries every 60 seconds. A failed, invalid,
or stalled feed falls back to the complete bundled snapshot. The top bar names
the source and shows its latest event timestamp, not the fetch time. Raw GitHub
CDN propagation can still delay updates. Clearing `VITE_FEED_URL` preserves the
original bundled-only behavior.

After each scheduled run's successful finish, abort, or saved calendar skip,
the runner starts `scripts/publish_feed.py --runtime runtime`. It exports only
the same scrubbed run logs, replaces `data/` in a temporary feed checkout, and
pushes a normal commit on `main`. It does not rewrite history. Publication is
best effort with a 30-second runner limit and a `feedPublished` boolean in the
phase JSON; failures cannot undo the completed save/unlock. The Git token is
passed in a child environment HTTP header, never a URL or command argument.

For a local export without Git or network access:

```powershell
.venv/Scripts/python scripts/export_dashboard.py --runtime runtime --out dashboard/public/data
```

Both export modes write `index.json` and `meta.json`. Metadata contains
`generatedAt` (export time), `latestEventTs` (latest included event or null),
and `logs` (the ordered filenames). The feed contains public, scrubbed data;
never point it at the private ledger repository.

## Data flow

1. The remote feed, when configured, or `public/data/index.json` lists the JSONL logs to load.
2. `src/data/load.ts` fetches each file, parses one event per line and assigns a
   global `gseq` after sorting events chronologically across the corpus. Parse
   failures are collected, not hidden.
3. `src/data/state.ts` exposes one pure reducer, `stateAt(events, seq)`. It folds
   events up to `seq` and rebuilds equity, cash, positions, tier, halts, orders,
   intents, vetoes/resizes, skips, ratings, shadow books, credits, drill results,
   rule changes and per-session summaries. "Live" is simply the latest `gseq`.
4. Views (`MissionControl`, `RiskDesk`, `MoverRadar`, `TruthTable`, `DebateRoom`)
   and the decision drawer read only that state object. Derived figures (marks,
   P&L, allocation, Wilson interval, credit pace) are computed in
   `src/data/metrics.ts`; Stage 2 radar, scorecard, bootstrap intervals and
   debate records are computed in `src/data/stage2.ts`. Neither is invented in a
   view.
5. `src/components/Trace.tsx` attaches the source event to numbers and text;
   the global tooltip shows event file, seq, type and timestamp.

## View links

Each view has a stable fragment: `#mission`, `#risk`, `#radar`, `#truth` and
`#debate`. Opening one of those URLs selects that view directly. Navigation
updates the address without a reload, and browser Back/Forward moves between
views. The `#main` skip link and unknown fragments leave the current view alone.

## Desk duck

`src/components/Duck.tsx` draws the original sticker duck as inline SVG; there is
no image file. It follows the pointer from its slot beside the brand, returns
home after eight seconds idle, then shows a small `z`. It flips to face its
movement, bobs while walking and hops when verification completes. The Duck
button stores the on/off choice in `localStorage`. Coarse-pointer devices and
`prefers-reduced-motion` park it at its slot with no animation, and the duck is
decorative (`aria-hidden`, `pointer-events: none`).

## Hash verification

The **Verify logs** button calls `src/data/verify.ts`. Scrubbed exports display
an explicit unverified status with zero events claimed as verified. For original
logs, it:

- parses each line while preserving the original numeric lexeme, so Python
  floats such as `1895.0` stay `1895.0` instead of becoming `1895`;
- serialises compact JSON with sorted keys (canonical form from
  `docs/event-contract.md`);
- recomputes SHA-256 with Web Crypto and compares it with the stored `hash`;
- checks each file's `prevHash` chain and file-local `seq`.

It reports OK or the first broken seq with a reason. This checks integrity, not
authentication: removing a complete suffix or rebuilding the whole chain cannot
be detected without a separately trusted terminal hash.

## Fidelity notes

- The bundled snapshot contains 31 real run logs (206 events), through
  2026-11-18T17:43:31.839369Z: IEF 218, XLP 40, ACM 130; cash $65,780.70.
- Real `core_rebalance` events are proposals; holdings change only on fills.
  Single researcher-rater calls and execution skips are shown without inventing
  debate calls. Null credit usage is unavailable, not zero.
- Operator restarts exist only in private state.json `restartReasons`. They are
  not exported or fabricated as events; the current halt latch is shown as unknown.
  Historical halt reasons and scrubbed differences remain visible.
- Position values use the last event print, not a market mark; the resulting
  mark-based equity does not fully reconcile with reported cash.
- Today's P&L and shadow returns require `daily_report`, absent from this snapshot.
- Broker snapshots and delayed fill-record timestamps can overlap. Cash at an
  intermediate replay point can include a fill before its event is recorded;
  latest cash is the last `run_started` snapshot, not a claim of exact intrarun reconciliation.
- There are no graded outcomes and no aligned 60-day return series in this
  snapshot, so the hit rate, calibration, call matrix and correlation cells are
  shown as unavailable rather than guessed.
- This snapshot has no bull/bear transcripts or graded outcomes.
  The Debate room shows one short "Not logged yet" line for each side; it does
  not reconstruct them. There is no quick-only shadow book for the head-to-head.
- Stage 2 market caps are a static excerpt of
  `config/universe-2026-11-16.json`; no network call fetches them.
- Fees are modelled from FEES-01 when showing net exit P&L; logged fills remain
  the source of truth.

## Layout

Always dark. Desktop uses a sidebar; at 900 px and below the navigation becomes
five fixed bottom tabs. The grid collapses to one column at phone width, wide
tables scroll inside their own box, focus rings are visible, and
`prefers-reduced-motion` disables animation/transition. ECharts animation is
always off in the option objects.

Stage 2 and the desk duck are complete: Mover radar, Truth table and Debate room
are built alongside Mission control and Risk desk wall. Stage 3 is not built.
