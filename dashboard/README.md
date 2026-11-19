# MooWoo Desk dashboard — Stage 2b + trading floor

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
4. Views (`MissionControl`, `RiskDesk`, `MoverRadar`, `TruthTable`, `DebateRoom`)
   and the decision drawer read only that state object. Derived figures (marks,
   P&L, allocation, Wilson interval, credit pace) are computed in
   `src/data/metrics.ts`; Stage 2 radar, scorecard, bootstrap intervals and
   debate records are computed in `src/data/stage2.ts`. Neither is invented in a
   view.
5. `src/components/Trace.tsx` attaches the source event to numbers and text;
   the global tooltip shows event file, seq, type and timestamp.

## View links

Each view has a stable fragment: `#mission`, `#risk`, `#radar`, `#truth`,
`#debate` and `#floor`. Opening one of those URLs selects that view directly.
Navigation updates the address without a reload, and browser Back/Forward moves
between views. The `#main` skip link and unknown fragments leave the current
view alone.

## Desk duck

`src/components/Duck.tsx` draws the original sticker duck as inline SVG; there is
no image file. It follows the pointer from its slot beside the brand, returns
home after eight seconds idle, then shows a small `z`. It flips to face its
movement, bobs while walking and hops when verification completes. The Duck
button stores the on/off choice in `localStorage`. Coarse-pointer devices and
`prefers-reduced-motion` park it at its slot with no animation, and the duck is
decorative (`aria-hidden`, `pointer-events: none`).

## Trading floor (`#floor`)

The floor replays one session event by event as an isometric voxel office. It is
built from three.js primitives only (`dashboard/src/components/Floor3D.tsx`):
boxes, cylinders and spheres, no models, textures or third-party art. The
orthographic camera is fixed-angle; dragging pans, wheel or pinch zooms between
0.72x and 2.35x, and **Reset view** restores the frame. There is one shadow-
casting light. Name tags, speech bubbles, cards, stamps and the tier screen are
HTML overlays projected from 3D positions. Frames render on demand (after a
change, while a short scene animation runs, or on interaction) and stop while
the tab is hidden.

Layout follows the work flow left to right in zones that use the whole floor.
Intake (Scheduler wall clock, Screener ticker board and the patrolling Watcher)
sits along the back-left wall; the research pod puts Analysts 1-3 around one
table; the debate pit has Bull and Bear facing each other across the round table
with the Manager between them; Decision holds the Quick kiosk and the Trader
desk; Controls holds the Risk booth with the APPROVED/RESIZED/VETO stamp and the
Core rebalancer; Execution puts the Executor by the "Moomoo paper" door; and the
back office (Auditor filing cabinet) sits in the bottom-right corner. The
Coordinator platform stays in the centre and the mascot with the backwards cap
and sunglasses free-roams the open floor in front of it; the **Duck** toggle
hides it.

Each duck reads at the default zoom. Agents keep yellow bodies with a distinct
silhouette or prop: Bull's horns and broad body, the Bear's round body and dark
cap, the Manager's tall hat, the Analysts' differently coloured clipboards,
Quick's small frame with a stopwatch, and the Trader's headset. Code steps
(Scheduler, Screener, Watcher, Risk desk, Executor, Core rebalancer, Auditor)
use a grey-white body with one coloured accent each. Name tags float above the
heads on a short leader line and fade to 50% while a replay event highlights
other ducks. Speech bubbles and rating/report cards are positioned in screen
space to stay clear of tags, wall overlays and each other; when the floor is
too crowded for a clear slot they dock at the top-left of the stage.

The equity/tier wall screen is unchanged. The big wall board lists only the
five core ETFs (USMV, XLP, XLV, IEF and GLD, blue chips); a smaller satellite
board beside it lists non-core holdings with a violet dot for drift and a teal
dot for bounce (grey when the sleeve is unclassified). The session fixtures
hold no drift or bounce names, so those two dot styles exist but cannot be
exercised by the bundled data.

`src/data/floor.ts` derives each scene purely from `stateAt(events, gseq)` and
`sceneAt(sessionEvents, index, eventState)`, so scrubbing backwards rebuilds the
same scene. Every fixture scene type is covered: run start, screen, debate and
quick ratings, shadow books, tier changes, order intents, risk approve/resize/
veto, submissions, fills, stop hits, halts, rule changes, drills, reflection
notes, core rebalancing and daily reports. There are no `outcome` events in the
fixtures, so that scene is implemented but never triggered.

Controls are play/pause/replay, 1x/2x/4x, a scrubber, **Next event** and the
session picker (same three sessions as the other views). Clicking a duck or its
tag lists the events that role handled; clicking a slip, position tile or debate
card opens the existing decision drawer.

The floor falls back to the flat still-frame map (`FloorMap2D`) at
`prefers-reduced-motion: reduce`, when WebGL is unavailable, or when the stage
is narrower than 600 px (for example a 360 px phone). The fallback replays the
same scenes and keeps the drawer, scrubber, picker and ticker line.

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
  contract, so the hit rate, calibration, call matrix and correlation cells are
  shown as unavailable rather than guessed.
- The event contract has no bull/bear, manager-transcript or outcome events.
  The Debate room shows one short "Not logged yet" line for each side; it does
  not reconstruct them. There is no quick-only shadow book for the head-to-head.
- The fixture screen lists KO at z -1.8 despite the |z| >= 2 gate, and 19 Nov
  NVDA is classed non-tradeable yet has a fill. Both contradictions are shown
  with notes rather than repaired.
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

Stage 2, the desk duck and the 3D trading floor are complete: Mover radar, Truth
table and Debate room are built alongside Mission control, Risk desk wall and
the floor replay. Stage 3 is not built.
