# MooWoo Desk dashboard: Option B

Read-only operations screen for simulated paper funds. Two questions guide the layout:
**Now:** what is happening? **Strategy:** is the approach working?

## Run and build

From dashboard/:

```powershell
npm install
npm run test
npm run check:data
$env:VITE_FEED_URL = 'https://raw.githubusercontent.com/xxycoc/MooWoo-Desk/dashboard-feed/data/'
npm run build
npm run preview -- --port 4173
```

Build runs TypeScript checking and Vite; output is dashboard/dist/. Preview serves
the production bundle locally. For development use npm run dev. No deployment,
feed publication, private ledger export, or secret is needed for dashboard work.
The existing full ECharts bundle can produce Vite's large-chunk advisory.

## Data contract

src/data/load.ts, state.ts (stateAt), and verify.ts retain their existing contracts.
VITE_FEED_URL is a public data directory, never a credential or broker endpoint.
The loader fetches index.json, metadata and the listed logs, merges them in timestamp
order and assigns gseq. App refreshes a configured feed every 60 seconds, avoids
overlapping loads, and aborts an outstanding load on unmount. A failed or invalid
feed falls back to the complete bundled snapshot; the source and last-event time
remain visible below the tabs. Refreshing the page without a configured URL uses
bundled data only. No private state or broker calls occur in the browser.

Holdings change only on fills, not order intents or core rebalance proposals.
Marks are last logged prices, not streaming quotes. Equity is the reducer's latest
reported equity; invested percent uses logged position value divided by that equity.
Open P&L is gross mark minus average cost times quantity. Snapshot cash and delayed
fill records can overlap; these are not intrarun broker reconciliation claims.

The bundled snapshot remains unchanged. To inspect exporter options from the root:

```powershell
python scripts/export_dashboard.py --help
```

The exporter requires --ledger-repo or --runtime, and --out. It also accepts --ref,
--until and --include-fixtures. Do not re-export private ledgers into a UI commit.
Its dedicated output directory is cleaned of stale log files. Original fixture
logs remain outside dashboard/public/data; fixtures must never be mistaken for real
paper results. The dashboard warns if a corpus includes fixture-labelled events.

Exports use allowlisted fields, redact private references and credentials, alias
order IDs and long numeric identifiers, and omit original hashes. If later
published, every bundled log is downloadable, including decisions, prices, quantities,
reasons and evidence headlines. Existing deployment/feed-publisher configuration
belongs to the repository's deployment documentation, not this browser app.

When state.json contains a boolean halted flag, meta.json also includes exactly:

```json
{
  "desk": {
    "halted": false,
    "haltReason": "",
    "tier": "normal",
    "updatedAt": "2026-11-19T01:00:00Z"
  }
}
```

haltReason uses the same redaction as log prose, then is limited to 240 characters.
Known private values from both state and logs are scrubbed from both outputs.
tier is normal, reduced, exits_only, kill, or null when absent. updatedAt is UTC
to whole seconds: the runtime file's modification time, or the last commit touching
state.json at the pinned ledger ref. No private state fields are copied wholesale.
Missing state or legacy state without halted omits desk; invalid typed state stops
the export before replacing any output. --until limits events only, not the state
snapshot. No state snapshot is inferred from those filtered events.

## Layout and navigation

The sticky top bar keeps MooWoo Desk, SIMULATED FUNDS, equity/return, the next run
and the desk duck visible. The health banner follows immediately, then two tabs.
Default/unknown hashes become #now. Legacy #mission, #risk and #floor map to #now;
#radar, #truth and #debate map to #strategy. Back/Forward works; #main remains the
keyboard skip link.

Now contains four KPIs, a small equity chart from run_started events, positions,
and the ten newest run groups with Show more in batches of ten. Each runId gathers
all its events, even when it has no run_started event. Results prioritize halt,
abort, calendar skip, filled BUY tickers, then ok. Here ok means no logged failure,
not proof of run completion or reconciliation. Click a ticker or run row to open
the decision drawer. The run drawer links to ticker decisions and recorded events;
the ticker drawer retains intent, risk verdict/checks, fills, stops and evidence.

Strategy contains one question per chart:

- Mover radar: z-score versus positive RVOL on a logarithmic axis, gate lines,
  classification colours, orange rings for traded names and a collapsed ranked
  list. Defaults to the newest screen-bearing session, not an empty watcher.
  Invalid/nonpositive RVOL stays in the list but cannot enter the log plot.
  Bubble size uses the existing static universe market-cap excerpt, not a live feed.
- Are we beating the simple alternatives? Orange book equity divided by the
  original $100,000, indexed to 100. Grey SPY/follow-all/fade-all lines use recorded
  daily_report baselinePct/shadowPct daily returns, compounded from 100. Rerun
  reports for the same New York day use the latest record. Missing fields are not
  zero returns: no later points are joined across a missing report field. Missing
  comparisons explicitly say they appear after the daily audit. No fake lines.
- Which stream made money? Signed gross **open** P&L for core, drift, bounce and
  total, plus unclassified when needed. This is not all-time net performance.
- Is the hit rate better than a coin? Closed position round trips from recorded
  fills, net of the reducer's modelled fees. Partial exits roll into the final
  closed position; duplicate cumulative fills do not add trials. Break-even is
  not a win. Wilson 95% bounds and a 50% reference line accompany the estimate.
  No closed trades, or an interval containing 50%, means can't tell yet.
  This is a trade scorecard, not a classifier-calibration or causal-significance claim.
- How deep is the drawdown? Run-start and daily-report equity below its running
  peak, starting at $100,000, with -2%, -4%, -6% risk lines. Intraday moves between
  snapshots are unknown.

Removed: Mission control wall, Debate room, standalone Truth table, risk-desk
wall, quick-classifier calibration, credits chart and retired agent step strip.
The active agents are coordinator, analyst and executor. Screener, risk desk,
watcher and auditor are code steps, not extra agents. Historical raw log evidence
is retained, not rewritten to pretend retired actors never existed.

## Health and schedule

Health uses the exported desk snapshot when available, not a live broker heartbeat
or a browser read of private state.json. The loader validates desk before use.
Precedence is:

1. **Red:** when meta.desk exists, only desk.halted=true shows HALTED followed by
   desk.haltReason (or reason not recorded when empty). desk.halted=false ignores
   historical halt events, including silent operator restarts. Without desk, retain
   the legacy event rule: a halt persists unless explicitly cleared by a manual
   restart, marked as a run-only abort, or followed by a later run_started event.
2. **Amber:** otherwise, the newest run contains run_aborted or the session-runner
   note Session aborted; or the last event is older than 45 minutes during US
   regular hours. An empty corpus during those hours also warns. Exactly 45
   minutes is not stale.
3. **Green:** otherwise Running normally. Outside market hours, silence alone
   does not warn. A halt or aborted latest run continues to warn outside hours.

Every state also shows the last run time/kind and next run, formatted in
Asia/Singapore and labelled SGT. Old feeds and bundled data still use event-based
health. A restarted desk becomes visible after the next successful feed export
and refresh; last-run result text remains the historical result of that run.

Schedule source is America/New_York on weekdays: morning 09:35; watchers on each
:00/:30 from 10:00 through 15:30; close watcher 15:55; audit 16:10. On 27 November
2026, watchers end at 12:30, close watcher is 12:55 and audit 13:10 for the 13:00
close. Regular-hours staleness uses 09:30 to the applicable close. Intl timezone
conversion handles DST and SGT date rollover. Slots strictly after now are shown.
This follows the supplied weekday schedule, not a full exchange holiday calendar;
calendar-skip events explain skipped scheduled runs.

## Visual system and accessibility

Dark solid panels; orange our book, yellow agents, blue core, violet drift, teal
bounce, grey comparisons; existing green/red profit, loss and risk conventions.
Numbers use monospace tabular figures. Strategy's stream/hit-rate panels share a
row on desktop; all panels stack on phones. At phone widths the next-run schedule
gets its own line. Positions stack ticker/sleeve/P&L above labelled qty/cost/last/stop;
run results wrap below time and kind. Inner scrolling is a fallback with a visible
sideways-scroll cue and keyboard focus when needed. Radar bounds leave room for
bubbles and rings. The page and drawer reserve bottom space for a host badge of
about 140 by 40 pixels, including the device's safe-area inset.
Keyboard focus stays visible, including
selects. Drawer traps focus, closes with Escape and restores the trigger.

The original SVG duck and its persistent toggle remain. Coarse-pointer devices
and prefers-reduced-motion park it; reduced motion also disables CSS transitions
and animation. ECharts animation is disabled. Charts include textual summaries.

## Verify logs

Verify logs now lives in the footer and uses the unchanged verification engine.
Scrubbed exports explicitly remain unverified, claiming zero original-chain events
verified. Original logs are canonicalized while preserving numeric lexemes and
checked for SHA-256, prevHash and file-local seq. Verification reports the first
broken sequence. Integrity is not authentication: suffix removal or rebuilding a
whole chain needs an independently trusted terminal hash to detect.

## Checks

npm test covers loader success/fallback/cancellation and operational selectors:
DST, weekend and early-close scheduling, state-driven and legacy halt/restart
precedence, invalid desk fallback, radar bounds, staleness, run
classification, closed trades, missing benchmarks and old hash routing.
npm run check:data exercises the real bundled corpus, reducer holdings, scrub
scan, original-chain verification/tamper detection and both new views via SSR.
These deterministic tests do not prove browser rendering or live-feed delivery.

### Option B acceptance check (19 November 2026)

- All 22 tests, the real-data check and the feed-configured production build passed.
  Build includes TypeScript checking; the ECharts chunk-size advisory remains.
- Inspected the served production Now and Strategy tabs at 360 and 1280 pixels,
  including lower Strategy charts. No horizontal page overflow; table contents
  scroll within their boxes. Corrected inherited tiny row-header text and clipped
  stale canvas dimensions while ResizeObserver catches up after viewport changes.
- Public feed loading and refresh were observed. A transient bundled fallback
  recovered on a later refresh; this does not establish continuous availability.
- Ticker/run drawers, visible focus, Shift-Tab containment, Escape/trigger focus
  restoration, show-more, footer verification and a legacy hash redirect checked.
  Full-screen mobile drawers retain the simulated-funds disclaimer.
- Reduced-motion CSS and duck media-query handling were inspected; OS-level
  reduced-motion emulation was not performed. ECharts animation stays disabled.
- No private ledger export, bundled-data change, push or deployment performed.
