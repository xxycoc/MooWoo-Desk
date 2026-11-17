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
