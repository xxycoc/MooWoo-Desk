# MooWoo Desk dashboard — Stage 1

Static operations screen for the paper-trading desk. It reads the three fictional
fixture logs and rebuilds every figure from the event stream. There are no API
keys, no broker connections and no outbound network calls.

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

## Data flow

1. `public/data/index.json` lists the JSONL logs to load.
2. `src/data/load.ts` fetches each file, parses one event per line and assigns a
   global `gseq` across the corpus. Parse failures are collected, not hidden.
3. `src/data/state.ts` exposes one pure reducer, `stateAt(events, seq)`. It folds
   events up to `seq` and rebuilds equity, cash, positions, tier, halts, orders,
   intents, vetoes/resizes, skips, ratings, shadow books, credits, drill results,
   rule changes and per-session summaries. "Live" is simply the latest `gseq`.
4. Views (`src/views/MissionControl.tsx`, `src/views/RiskDesk.tsx`) and the
   decision drawer read only that state object. Derived figures (marks, P&L,
   allocation, Wilson interval, credit pace) are computed in
   `src/data/metrics.ts`, never invented in a view.
5. `src/components/Trace.tsx` attaches the source event to numbers and text;
   the global tooltip shows event file, seq, type and timestamp.

## Hash verification

The **Verify logs** button calls `src/data/verify.ts`, which:

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

- The fixtures are fictional seed-7 logs, not a reconciled replay.
- Position values use the last event print, not a market mark; the resulting
  mark-based equity does not fully reconcile with reported cash.
- Today's P&L and shadow returns come from `daily_report`; the fixtures repeat
  the same shadow percentages each session.
- There are no graded outcomes and no aligned 60-day return series in the event
  contract, so the hit rate and correlation cells are shown as unavailable
  rather than guessed.
- Fees are modelled from FEES-01 when showing net exit P&L; logged fills remain
  the source of truth.

## Layout

Always dark. Desktop uses a sidebar; at 900 px and below the navigation becomes
fixed bottom tabs. The grid collapses to one column at phone width, wide tables
scroll inside their own box, focus rings are visible, and
`prefers-reduced-motion` disables animation/transition. ECharts animation is
always off in the option objects.

Stage 1 only. Mover radar, Truth table and Debate room are Stage 2 and are not
present here.
