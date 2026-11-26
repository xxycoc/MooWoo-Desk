# Deck prompt for Qoder (submission deck)

Paste Stage 1 into Qoder in this workspace (`C:\Users\Woo\MooWoo-Desk-07`, branch `build/32-deck`). Paste Stage 2 on 28 Nov, after `docs/results.md` exists.

---

## Stage 1: build the deck

Build the submission deck for MooWoo Desk as one static HTML presentation in a new folder `deck/`.

### Who it is for

Judges of the Moomoo x Qoder AI Paper Trading Agent Challenge. Many are not engineers. They score risk-adjusted return (25%), Qoder and Cloud Agent use (30%), strategy and risk design (30%), reuse and documentation (15%). The deck must let a non-engineer follow the story in one pass.

### Writing rules (most important)

- Tell a story. One idea per slide. Each headline is a full sentence that states the point, not a label. "The desk has rules for saying no, and it used them", not "Risk management".
- Use the slide text below as written. You may shorten it. Do not add claims, numbers or adjectives.
- Plain words. Never use: agentic, leverage, seamless, cutting-edge, revolutionise, unlock, robust, synergy, empower, harness, game-changer, next-generation, AI-powered.
- No numbers that are not in this prompt or in repo files. Values marked `[28 Nov]` stay as visible placeholders until Stage 2.
- No emoji. No exclamation marks.

### Look (style C, "notebook with ducks")

- Slide: 16:9, 1280 × 720 design size, scaled to fit the window with letterboxing.
- Background warm paper `#f7f3ea`. Text `#2a2620`. Muted text `#7a705f`. Rules and borders `#d8ccb4`. One accent `#c25a1c` (orange) for the single thing to look at on each slide. Green `#3f7d4e` only for gains, red `#b23b2e` only for losses.
- Headlines: Georgia (fallback "Times New Roman", serif), regular weight, 40-44 px. Body and labels: "Segoe UI", system-ui, sans-serif, 20-24 px, never below 16 px. Small uppercase kicker above the headline in `#8a6d3b`, 14 px, letter-spacing 0.08em.
- Ducks: the three duck SVGs in `docs/images/` are the narrators. At most one duck per slide, about 88 px, top-right corner. Coordinator for timetable, results and Qoder slides; Analyst for news and rating slides; Executor for order and trade slides. Title slide uses `docs/images/ducks-banner.svg`. Slides 8-10 (numbers) and 16 have no duck.
- Generous white space. Left-aligned. Thin rules instead of boxes. No gradients, glows, shadows, glass, rounded "cards", icon grids, stock photos, 3D, or decorative shapes. No animated text. Slide change may fade (150 ms) and must respect `prefers-reduced-motion`.
- Charts: hand-written inline SVG. No chart library. Plain axes, labelled directly at the line ends, no legend boxes.

### Technical

- `deck/index.html`, `deck/deck.css`, `deck/deck.js`, `deck/data.json`. Copy the images you use into `deck/img/`. No CDN, no npm, no external fonts; it must open offline from the file system and also work when hosted on Qoder Sites.
- All numbers and table rows live in `deck/data.json`, so Stage 2 only edits data. A `null` value renders as a muted `[28 Nov]` tag.
- Navigation: right/left arrows, space, page up/down, click right/left half. `#5` in the URL opens slide 5. Slide number bottom-right in muted text. `p` toggles a speaker-notes panel (notes from the "Say" lines below). Print stylesheet: one slide per page, so Ctrl+P gives a PDF.
- Accessible: real text (not images of text), alt text on images, contrast at least 4.5:1.

### Slides

**1. Title**
Headline: "MooWoo Desk: AI reads the news. Code handles the money."
Sub: "Moomoo x Qoder AI Paper Trading Agent Challenge · Siang Woo · 17-27 Nov 2026". Duck banner below.
Say: A paper-trading desk that ran on its own for eight trading days.

**2. Kicker: The question** (Analyst)
Headline: "When a stock suddenly jumps or drops, is there a reason?"
Body: "On 19 Nov, Woodward (WWD) rose 8% on three times its usual volume. The reason was in that morning's news: earnings came in 13% above forecasts." Then: "Some big moves have a clear reason. Others don't. We bet that the difference matters."

**3. Kicker: Our bet** (Analyst)
Headline: "Moves with a clear reason tend to keep going. Drops without one tend to bounce back."
Visual: a 2 × 2 grid. Rows: Up / Down. Columns: Reason in the news / No clear reason.
- Up + reason: "Buy and ride it" (accent)
- Down + no reason: "Buy the bounce" (accent)
- Up + no reason: "Stay out"
- Down + reason: "Stay out"
Footer: "We wrote these rules down on 16 Nov, before the first trade, so we could not bend them after seeing results."

**4. Kicker: The desk** (no corner duck; show all three ducks in a row with labels)
Headline: "Three AI agents do the reading. Python makes every money decision."
Coordinator: "Runs the timetable". Analyst: "Reads the news and rates the move". Executor: "Sends only orders that code approved".
Below, smaller: "A fourth agent, the Auditor, checks the books every evening. It has no way to trade."
Bold line at the bottom: "No AI agent ever chooses what to buy or how much."

**5. Kicker: A trade, start to finish** (Executor)
Headline: "Woodward jumped 8% on an earnings beat. Here is what the desk did with it."
Five steps in a row, thin rule above each, last one in accent:
1 Spotted: "+8% on 19 Nov, 3× usual volume"
2 Read the news: "Analyst: earnings beat, 'explained up', 84% sure"
3 Sized by code: "24 shares, about $7,900"
4 Bought: "Filled 20 Nov at $327.59"
5 Exit: `data.wwdExit` (null until Stage 2)
Footer: "The analyst never picked the number of shares. Python did."

**6. Kicker: Where the money sits** (Coordinator)
Headline: "Most of the money sat in steady funds. Only part chased news."
Visual: one horizontal stacked bar of the planned split: Safe-haven funds 30% (USMV, XLP, XLV, IEF, GLD), S&P 500 fund 30% (SPY), News trades up to 30% (shown as "the rest, when cash allows"), Cash kept at least 10%. Accent on News trades.
Footer: "If the news idea is wrong, most of the account still follows the market."
Say: The rules allow news trades up to 60%, but in practice they are what is left after the core, SPY and the cash floor.

**7. Kicker: Saying no** (Coordinator)
Headline: "The desk has rules for saying no, and it used them."
Two-column table "If this happens" / "The desk does this":
- "The market is weak (S&P 500 below its recent trend)" / "Blocks new news trades. Blocked Disney and Target on 19 Nov and PDD on 23 Nov."
- "The account loses 1.5% in a day" / "No new buys until tomorrow."
- "The account is down 2%, 4% or 6%" / "Smaller trades, then sells only, then sell everything."
- "A trade rises by a normal day's move" / "Lock in profit with a stop that follows the price up."
- "A trade goes nowhere for 5 days" / "Sell it."

**8. Kicker: Results** (no duck)
Headline: from data, pattern "Over 8 trading days the account returned {return}, against {spyReturn} for the S&P 500."
Visual: line chart of daily closing account value 17-27 Nov (`data.equity`, accent) and SPY rebased to $100,000 (`data.spy`, muted). Start line at $100,000 dashed.
Three numbers under the chart: Return, Sharpe ratio, Largest drop.
Until Stage 2, plot only these known closes and label the chart "to 25 Nov": 17 Nov 100000 (start), 20 Nov 98562, 23 Nov 101322, 24 Nov 101074, 25 Nov 101086. Missing days are gaps, not interpolated.

**9. Kicker: Every trade** (no duck)
Headline: "Every news trade, and what it taught us."
Table from `data.trades`: Stock · Why we bought · Result · Lesson. Known row now: ACM · "Earnings beat, rated explained up" · "Sold after 5 days, about −$300" · "Good news, flat price: the time limit got us out." Other rows (WWD, PDD, NVDA) null until Stage 2.

**10. Kicker: Did the news help?** (no duck)
Headline: `data.verdictHeadline` (null until Stage 2).
Visual: three short bars: "Our news-rated calls", "Always follow the move", "Always bet against the move". Values from `data.verdict`. Footer: "Eight days is a small sample. We report it as it is."

**11. Kicker: What broke: day one** (Coordinator)
Headline: "On the first day, 13 attempts produced zero trades."
Body, three short lines: "Too many agents argued (bull, bear, manager and more) and passed long text to each other." / "Answers came back as essays instead of clean data." / "We cut it to one analyst giving short, strict answers. The next day the desk traded."

**12. Kicker: What broke: the brakes** (Executor)
Headline: "The desk stopped itself twice. Both times, stopping was the right call."
Simple two-point timeline:
- 18 Nov: "A copied broker record lost a field. The desk refused to guess and stopped."
- 25 Nov: "A sell order filled in two parts and looked like a mismatch. The desk stopped."
Under both: "No bad trade was made. Each time: find the cause, fix it, write it down, add a test."
Footer: "A desk that stops when unsure is safer than one that guesses with money."

**13. Kicker: Lessons** (Analyst)
Headline: "What we would do differently."
Three numbered lines: "Start with one agent and one full day, then add more." / "Treat every broker reply as possibly wrong." / "Build the audit trail before the trading logic."

**14. Kicker: How Qoder ran it** (Coordinator)
Headline: "Qoder ran the desk every 30 minutes without anyone pressing a button."
Left, a short list: "4 Cloud Agents" / "6 schedules: morning, every 30 minutes, close, audit" / "Dashboard and 3D trading floor built in Qoder, hosted on Qoder Sites" / "Evening summary posted to Slack by the Auditor" / "Credits used: {credits}" (null until Stage 2).
Right: `docs/images/trading-floor.png`, alt "The trading floor replaying a real session".

**15. Kicker: Reuse it** (Coordinator)
Headline: "Anyone can rerun the desk or borrow its parts."
Three lines: "GitHub: github.com/xxycoc/MooWoo-Desk" / "15 reusable skills, such as market regime, risk desk and news-vs-noise" / "Rules written before trading, every decision logged, tests for every fix". Second line of links: "Live dashboard: moowoo-desk-p36f61ggjia.qoder.website".

**16. Kicker: Honest summary** (no duck)
Headline: "What we claim, and what we don't."
Two columns. "We claim": "A desk where code, not AI, controls the money." / "It ran on its own for 8 trading days." / "Every decision is on record." "We don't claim": "A proven way to beat the market. Eight days is too short to know."

### Before you finish

- Open `deck/index.html` in a browser at 1280 × 720 and 1920 × 1080. Every slide fits with no overflow and no text below 16 px.
- Search the deck for the banned words above and remove any.
- Check every number on the slides against this prompt or `deck/data.json`.
- Commit on `build/32-deck` as "Add submission deck (Stage 1)". Do not push.

---

## Stage 2 (28 Nov): fill the numbers

Read `docs/results.md` and the generated results files in `docs/`. Fill every null in `deck/data.json`: full daily equity and SPY series 17-27 Nov, return, SPY return, Sharpe, largest drop, credits, WWD exit, the trades table (WWD, PDD, NVDA rows plus ACM), and the follow/fade comparison with `verdictHeadline`. Write the slide 8 and slide 10 headlines as plain sentences from the actual numbers, even if the result is a loss or "too few trades to tell". Do not change any other slide text. Re-run the checks above, then commit "Fill deck results (Stage 2)". Do not push.
