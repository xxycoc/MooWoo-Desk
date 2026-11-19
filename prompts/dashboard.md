# MooWoo Desk dashboard: Qoder build prompts

Built by Qoder (Desktop) so the dashboard itself counts as Qoder usage. Paste one stage at a time into a NEW Qoder chat, with the workspace folder set to `C:\Users\Woo\MooWoo-Desk-07` (branch `build/09-dashboard`, already prepared). Check the result in the browser before the next stage. Claude reviews each stage's diff before it is merged.

Never paste a Qoder PAT, Moomoo token or account ID into these chats. Stage 3 reads them from `.env` on the server side only.

---

## Stage 1: shell, data layer, Mission control and Risk desk wall

```
Build a web dashboard in the folder dashboard/ of this repo for "MooWoo Desk", my AI paper-trading agent desk in the Moomoo x Qoder AI Trading Agent Challenge. The dashboard shows decisions, not just returns: every number must trace back to the event that produced it.

Read these files first: docs/event-contract.md (the event log format), fixtures/2026-11-17-us.jsonl, fixtures/2026-11-18-us.jsonl, fixtures/2026-11-19-us.jsonl (sample logs), docs/risk-desk.md (the rules and limits), PREREGISTRATION.md (the strategy and limits), moowoo/config.py (thresholds).

Stack: Vite + React + TypeScript, Apache ECharts for charts. No other UI framework. Static build output in dashboard/dist.

Data layer first:
- Load every JSONL event log listed in dashboard/public/data/index.json (copy the three fixtures there for now).
- Write a pure function stateAt(events, seq) that rebuilds the full desk state as of any event: equity, cash, positions (core / drift / bounce), tier, halts, orders, vetoes, skips, ratings, shadow books, credits. Every view reads only from it. "Live" means the latest seq.
- Verify button: recompute each event's sha256 hash with the Web Crypto API and check the prevHash chain exactly as docs/event-contract.md describes; show OK or the first broken seq.
- Hovering any number shows the event it came from (seq, type, ts).

Look (fixed; do not change these colours or their meanings):
- Always-dark operations screen. Background #0c1322, panels #121b2e, lines #24314a, text #e8edf6, muted #8b97ad.
- Orange #ff7a1a = our book and its trading (equity line, entries, orders).
- Yellow #f2c230 = agents and their work (agent steps, news cutoff, credits).
- Blue #5b8def = core sleeve, violet #a78bfa = drift trades, teal #2dd4bf = bounce trades.
- Grey #8b97ad = comparisons (SPY and the shadow books), told apart by dash pattern and labels at the line ends.
- Green #34c98a = up, approved, passed. Red scale #fca5a5 / #f26b6b / #c92a2a = down, vetoed, and risk tiers reduced / exits only / kill.
- Solid panels only: no gradients, glow, glass blur or decorative animation. Numbers in a monospaced font with tabular figures. "SIMULATED FUNDS" label always visible.

Shell (every view): top bar with MooWoo Desk, SIMULATED FUNDS, US session state and countdown to the next run (21:30 Asia/Singapore), equity and today's P&L, a 4-step risk tier scale (Normal / Reduced / Exits only / Kill), config hash and prompt version. Side navigation on desktop, bottom tabs on phone. One decision drawer opened from anywhere (click a ticker, order or veto): screen row, analyst facts with publish times, bull and bear, verdict, sizing maths, risk verdict with rules checked, order, fill, stop, exit.

View 1, Mission control. Pick each chart for its question:
- "Are we beating the simple alternatives?" Line chart, all lines indexed to 100 at the start: our book (orange, thick), equal weight, SPY, follow-all, fade-all (grey, different dash patterns), labels at the line ends instead of a legend. Markers on the time axis for drills (D), vetoes (V) and rule changes (R).
- "How deep is the drawdown?" Underwater area chart from peak with dashed lines at -2, -4 and -6% in the red scale, labelled.
- "Is the money where the plan says?" Two stacked bars, actual over target: core / drift / bounce / cash against 50 / 25 (satellite) / 25.
- "Which stream made money?" Signed horizontal bars from zero for core, drift, bounce and total.
- "Is the hit rate better than a coin?" A point with its 95% Wilson interval on a 0 to 100% axis with a dashed line at 50%; if the interval crosses 50%, say "can't tell yet".
- "How close is each limit?" Bullet bars with a limit mark: largest position vs 8%, satellite vs 25%, today's loss vs 1.5%, max correlation vs 0.80, orders vs 30.
- "Will credits last?" Cumulative credits line with a dashed pace projection and a dashed budget line at 3,500.
- Today's run as an ordered strip of steps (schedule, screen, analysts, debate, quick, risk desk, executor, watcher, auditor), yellow top border for agent steps, grey for code steps, each Done / Running / Waiting.

View 3, Risk desk wall: a feed of order intents stamped APPROVED, RESIZED or VETO with the rule that fired; a correlation heatmap of open positions with cells above 0.80 outlined; the drill board (date, drill, expected, observed, pass or fail); the kill switch status and last restart reason.

Layout must work at 1280 px and at 360 px wide with no horizontal page scroll (wide tables scroll inside their own box). Visible keyboard focus. Respect prefers-reduced-motion.

Run it locally (npm install, npm run dev) and give me the URL. Add dashboard/README.md with how to run and how data flows. Do not add any API keys or network calls yet.
```

## Stage 2: Mover radar, Truth table, Debate room

```
Continue the dashboard in dashboard/. Keep the stack, the data layer (stateAt) and the colour code exactly as they are.

View 2, Mover radar:
- Bubble chart of every screened stock in the selected session: x = move z-score (negative left, positive right), y = relative volume (RVOL, log scale), bubble size = market cap, colour by class (explained up, explained down, unexplained up, unexplained down; skips greyed), a ring around stocks we traded. Draw the gate lines: |z| = 2, RVOL = 2 (drift needs at least this), RVOL = 3 (bounce needs less), with small zone labels.
- Universe funnel beside it: all names, gated universe (727), movers, top 15, traded, with how many dropped at each step and why.
- Ranked list; clicking any row or bubble opens the decision drawer.

View 4, Truth table:
- Pre-registration scorecard: H1 classification, H2 value over simple rules, H3 calibration, each with its verdict (supported / rejected / can't tell yet) computed with the exact rules in PREREGISTRATION.md.
- Calibration chart: confidence bins against actual hit rate, diagonal = perfect, one line for the debate and one for the quick classifier, Brier score.
- Call matrix: predicted class against what the stock then did, skips included.
- Head to head on the same movers: our book, quick classifier, follow-all, fade-all.
- Return, Sharpe, Sortino, Calmar and max drawdown with their 95% intervals; Sharpe first, since the organisers score risk-adjusted return by Sharpe.

View 5, Debate room: analyst facts on a timeline with the news cutoff drawn as a yellow line, bull and bear side by side, the manager's verdict with a confidence bar, the quick classifier's call, an agreement count, "what would prove me wrong", and after the horizon the outcome and process checklist.

Keep everything responsive at 360 px and run it locally again.
```

## Stage 3: live data and hosting

```
Connect the dashboard in dashboard/ to live data, without exposing any secret in the browser.

- Add a small server (dashboard/server/, Node) that the browser calls. It reads QODER_PAT, MOOMOO_ACCOUNT_ID and MOOMOO_MARKET from the repo's .env (already gitignored); never send them to the browser or log them.
- From Qoder Cloud Agents (https://api.qoder.com/api/v1/cloud, Authorization: Bearer from the server only): latest sessions and events for my MooWoo agents, their status and credits used.
- Paper account data comes from the files the auditor writes after each run (positions, orders, cash, P&L in ledger/), not from direct broker calls in the dashboard.
- The browser polls the server every 60 seconds while US markets are open.
- Then help me publish the static part to Qoder Sites and keep the server side local, and tell me exactly what is public and what stays private.
```

## Stage 4 (stretch, only if time allows)

```
Add three views to dashboard/, same rules as before:
1. Agent org chart: a graph of the agents (coordinator, analyst, bull, bear, manager, quick, executor, auditor) and code steps (screener, sizer, risk desk, watcher), nodes lighting up as their events arrive, with calls, credits and error counts per node.
2. Replay: a scrubber over the whole log with play, pause and speed; every view follows the selected seq through stateAt.
3. Learning timeline: each failure, the agent blamed, the fix (rule ledger entry and prompt diff), the replay test result and the live effect before and after.
```

---

## Credit estimate
Stage 1: about 80 to 180 credits. Stage 2: 60 to 120. Stage 3: 40 to 100. Stage 4: 60 to 120. Stages 1 to 3 together: roughly 180 to 400 of 3,500. Check the console after stage 1.

## Stage 2b: the desk duck (mascot)

```
Add a small mascot to the dashboard in dashboard/: an ORIGINAL 2D duck drawn as inline SVG in code (do not copy or trace the Qoder mascot or any other brand artwork). Body Qoder yellow #f2c230, beak and feet Moomoo orange #ff7a1a, eye #0c1322, a thin darker outline so it reads on the dark background. About 28 px tall.

Behaviour:
- On load it sits next to the "MooWoo Desk" title in the top bar, idling with an occasional blink.
- When the mouse moves, it waddles after the cursor with a gentle lag (smooth easing, e.g. lerp each animation frame), staying about 24 px below and to the right of the pointer, never on top of it. It faces the direction it is moving (flip horizontally) and uses a simple 2-frame waddle bob while moving.
- After 8 seconds without mouse movement it waddles back to its spot by the title and sits down (small "z" after a while).
- Small delight, only one: when "Verify logs" returns OK, it does one little hop.
- It must never get in the way: pointer-events none, z-index below tooltips, the decision drawer and any modal; it never covers the number the pointer is hovering (keep the offset).
- Touch devices (no hover / coarse pointer): it stays parked by the title and does not follow.
- prefers-reduced-motion: parked by the title, no following, no animation.
- A small toggle in the top bar ("Duck on/off"), remembered in localStorage inside try/catch; off by default only if localStorage says so.
- Performance: one requestAnimationFrame loop, paused when the tab is hidden or the duck is parked and idle; no libraries.
Put it in dashboard/src/components/Duck.tsx with its SVG, and mention it in dashboard/README.md. Keep everything else unchanged. Run it locally and give me the URL.
```

### Stage 2b restyle (sent after 2b)

```
Restyle the desk duck in dashboard/src/components/Duck.tsx; keep all behaviour unchanged. Style reference described in words (do not copy or trace any existing image): a chunky glossy rubber duck in side view, sticker style, with a backwards black baseball cap, black wayfarer-style sunglasses with a small white glint, a wide slightly open orange beak (#ff7a1a, darker orange inside), yellow body (#f2c230) with a lighter highlight on head and wing, a short tucked wing, a thick near-black outline and a thin light outer edge. Original inline SVG, simplified to read clearly at about 36 px tall. Walking: bob and tilt the whole sticker slightly. Dozing: sunglasses stay on, small "z". Face the direction of travel.
```

## Stage F: Trading floor view (the game, inside the dashboard)

```
Add a sixth view to the dashboard in dashboard/: "Trading floor", in the side nav after Debate room and in the phone bottom tabs, with its own link #floor. It shows the agents at work as a small top-down 2D office, replaying the event log. Keep everything else unchanged, including the colour code, the data layer (stateAt) and the desk duck.

Rendering: one <canvas> drawn with plain TypeScript (no game engine, no new libraries, no image files). Shapes and text only: characters are simple rounded figures with a name tag; desks are rounded rectangles. Dark navy floor (#0c1322), desks (#121b2e), lines (#24314a), text (#e8edf6). Scales to the panel width; at 360 px it shows the whole floor smaller with a "rotate for a bigger view" hint.

Desks, left to right in the order work flows:
Scheduler, Screener (a board of tickers), Analysts (3 desks), Debate table (Bull, Bear, Manager), Quick classifier (small kiosk), Trader, Core rebalancer, Risk desk, Executor (beside a door labelled "Moomoo paper"), Watcher (walks a patrol loop), Auditor (beside a filing cabinet), Coordinator (centre, overlooking the floor).
Colours: yellow #f2c230 = agents (analysts, bull, bear, manager, quick, coordinator, auditor); grey #8b97ad = code steps (scheduler, screener, trader, rebalancer, risk desk, executor, watcher); orange #ff7a1a = our orders (order slips, position board); blue #5b8def core, violet #a78bfa drift, teal #2dd4bf bounce for position tiles; green #34c98a approved/passed; red #f26b6b vetoed/stop/failed.

Scenes, driven by the same events the other views read (1 to 3 seconds each at 1x):
- run_started: lights on, the Scheduler rings a bell, equity on a wall display.
- screen: tickers light up on the Screener board; picked ones rise to the top.
- rating: an Analyst carries a paper to the Debate table; Bull and Bear show short speech bubbles (bullSummary / bearSummary when present, else "…"); the Manager raises a card with class and confidence. tier "quick": the paper goes to the Quick kiosk, which flashes its answer.
- order_intent: the Trader writes an orange slip and walks it to the Risk desk.
- risk_verdict: the Risk desk stamps APPROVED (green), RESIZED (amber) or VETO (red) with the rule name; vetoed slips drop in a bin.
- order_submitted / fill: the Executor takes the slip through the "Moomoo paper" door; on fill a tile in its sleeve colour lands on the position board.
- stop_hit: the Watcher blows a whistle; the tile turns red and leaves the board.
- tier_changed: the floor lighting shifts (normal, amber, deep red) with a banner.
- drill: a "DRILL" banner with expected vs observed and PASS/FAIL.
- outcome: a small tick or cross pops above the decision's tile.
- daily_report: the Auditor files the report; a summary card shows equity and P&L.

Controls: play, pause, speed 1x/2x/4x, a scrubber over the session's events, "next event", and a session picker (same sessions as the other views). A ticker line along the bottom describes the current event in plain words. Clicking a character lists the events it handled; clicking a slip, tile or debate card opens the existing decision drawer. Scrubbing backwards must rebuild the correct scene from stateAt (no state that cannot rewind).

The desk duck: on this view it waddles onto the floor and stands beside the Coordinator as the floor's mascot instead of following the cursor; it still respects reduced motion and the Duck on/off toggle.

prefers-reduced-motion: no walking; scenes switch as still frames with the ticker line. Pause the animation loop when the tab is hidden.
Done when the 19 Nov fixture replays every scene type without console errors, scrubbing back works, and the view passes the 360 px check. Update dashboard/README.md. Run it and give me the URL.
```

### Stage F revision: 3D voxel office with the duck crew (use this instead of the 2D canvas rendering above; scenes, controls and data rules stay as written)

```
Build the Trading floor view as a small 3D isometric office in the style of a low-poly / voxel game (our own design; do not copy any existing product's layout, signage or branding).

Tech: three.js (add the npm package to dashboard/; no other new libraries, no external model or texture files). Everything is built from boxes, cylinders and spheres in code. Orthographic camera at a fixed isometric angle; drag to pan, wheel or pinch to zoom within limits, a "reset view" button; no free 360 orbit. Soft lighting with one shadow-casting light. Name tags are HTML overlays above each duck (dark pill, role name, small status dot: grey idle, yellow working, green done, red problem). Keep the frame rate light: render on demand when something moves, pause when the tab is hidden.

The office (left to right in work order): a wooden floor and low walls; Scheduler by a wall clock; Screener at a big ticker board on the back wall; three Analyst desks with monitors; a glass-walled Debate room with a round table (Bull, Bear, Manager); a small Quick kiosk; Trader desk; Core rebalancer desk; Risk desk in a booth with a big APPROVED / RESIZED / VETO stamp; Executor beside a door labelled "Moomoo paper"; Watcher patrolling the aisle; Auditor at a filing cabinet; Coordinator on a raised platform in the centre. A position board on one wall shows tiles in sleeve colours (blue core, violet drift, teal bounce). A small lounge corner with a sofa and a plant for life. Wall screen shows equity and the risk tier; the whole office lighting tints amber or deep red when the tier changes.

The duck crew (voxel ducks built from blocks; body yellow #f2c230 = LLM agent, light grey #c3ccdc = code step; orange #ff7a1a beak and feet; each role recognisable by silhouette first):
- Analyst: round glasses, blue beret, holds an open newspaper.
- Bull: green horned helmet, leans forward, small up-arrow flag.
- Bear: red bear-ear hood, arms crossed, down-arrow sign.
- Manager: slightly larger, black top hat with violet band, gavel.
- Quick: tiny duckling with a lightning bolt, moves fastest.
- Coordinator: headset with mic, clipboard.
- Auditor: violet bow tie, magnifying glass.
- Scheduler (grey): alarm clock on its head.
- Screener (grey): binoculars raised.
- Trader (grey): green eyeshade, pencil behind the ear, orange order slip.
- Risk desk (grey): green banker visor, giant red stamp.
- Executor (grey): orange courier cap and backpack, carries slips through the Moomoo door.
- Watcher (grey): dark patrol cap, flashlight with a soft beam, whistle.
The mascot desk duck (backwards cap and sunglasses) stands beside the Coordinator's platform as the office mascot.

Animation: ducks waddle (bob and side-to-side tilt) between desks along simple paths; speech bubbles are HTML overlays; stamps, slips and tiles are small 3D objects that move. All scenes from the 2D spec play the same way in 3D.

Fallbacks: prefers-reduced-motion, no WebGL, or width under 600 px -> show the 2D still-frame version (desk map with name tags and the ticker line), same controls.

Keep the decision drawer, the scrubber, session picker, speed controls and #floor link. Done when the 19 Nov fixture replays every scene type, scrubbing back rebuilds the scene, no console errors, and the fallback works at 360 px. Update dashboard/README.md. Run it and give me the URL.
```
