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

## Stage 1b: review fixes (27 Nov)

Fix these in `deck/`, then re-run the Stage 1 checks and commit "Deck review fixes (Stage 1b)". Do not push.

### 1. Fill the slide (most important)
Every slide uses only the top half; the bottom half is empty and the text is too small for a projector.
- Raise the type scale: headline 52-56 px, body and table text 26-28 px, small notes and footers at least 20 px, kicker 16 px.
- Spread each slide's content over the full height: headline at the top, the main visual or table taking the middle, footer line near the bottom. No slide should have more than about a quarter of its height empty.
- Slide 1: centre the title block vertically. Replace the dark banner image with the three duck SVGs side by side on the paper background (about 140 px each) with their names under them. No dark box.
- Slide 8: the chart takes most of the slide height.

### 2. Correct the facts
The ledger shows the desk stopped itself five times, not twice, and a person restarted it each time. Change:
- Slide 12 headline: "The desk stopped itself five times. Each time, it stopped rather than guessed."
  Replace the two-point timeline with five short points, in order:
  - 18 Nov: "The broker named a price field differently from what we expected."
  - 18 Nov: "Cash and holdings were read seconds apart, prices moved, and the totals were $9.75 apart."
  - 18 Nov: "A copied broker record lost a field."
  - 20 Nov: "After a part-sale, the broker's average cost differed from ours."
  - 25 Nov: "A sell order filled in two parts and looked like a mismatch."
  Keep the line "No bad trade was made. Each time: find the cause, fix it, write it down, add a test." and add "Then a person restarted the desk."
  Keep the footer "A desk that stops when unsure is safer than one that guesses with money."
- Slide 14 headline: "Qoder ran the desk on a timetable: a check every 30 minutes, all day." (It did need people to restart it, so do not say "without anyone pressing a button".)
- Slide 16, "We claim" second line: "It traded on a schedule for 8 days. People only restarted it after it stopped itself."
- Speaker note for slide 1: "A paper-trading desk that ran on a schedule for eight trading days."

### 3. Chart
Slide 8 draws a straight line from 17 Nov to 20 Nov across the missing 18 and 19 Nov closes. Break the line where days are missing (draw separate segments), as the Stage 1 prompt asked.

### 4. Speaker notes
Write a note for every slide: one to three plain sentences that say what to point at and why it matters. Use only facts already on the slide or in this prompt. Store them in `data.json` `notes`.

### 5. Offline copy stays in sync
Add `deck/sync_data.py` (standard library only) that copies `deck/data.json` into the inline snapshot in `deck/index.html`, and fails loudly if the snapshot markers are missing. Run it now and mention it in a short `deck/README.md` (how to open, keys, how to update numbers).

---

### Final-day failure (added 28 Nov, applies to Stage 2)

The desk did not sell its holdings before the 27 Nov close. The organiser said to disclose it in the report. Show it plainly:
- Slide 8: show two numbers side by side, "Account value at the close: $101,942 (+1.9%)" and "Locked in (realised): about -$242". Add one line under them: "Nine holdings were never sold. See slide 12." Headline from the real figures, for example "The account ended up 1.9%, but most of that gain was never locked in."
- Slide 12: add a sixth point, in accent colour: "27 Nov: one quiet ETF's price was 106 seconds old. The 60-second check stopped the final sell-off twice, and the last retry started after the close. Nine holdings were never sold." Change the headline to "The desk stopped itself six times. The last time, it cost us the final sell-off." Replace "No bad trade was made." with "No bad trade was made, but the last stop meant no final sale."
- Slide 13: add a fourth lesson: "Test the last day on its own. It only had three chances to work."
- Slide 16, "We claim": keep the lines; under "We don't claim" add "A clean finish: the final sell-off failed, and we said so."

## Stage 2 (28 Nov): fill the numbers

Final numbers, all from `docs/results.md`, `docs/post-mortem.md` and `docs/qoder-usage.md` on this branch. Use exactly these:

- `equity` (daily close, USD): 17 Nov 100000, 18 Nov 99903, 19 Nov 99625, 20 Nov 98562, 23 Nov 101322, 24 Nov 101074, 25 Nov 101086, 27 Nov 101981. No gaps now; set `chartLabel` to "17-27 Nov".
- `spy` (SPY rebased to USD 100,000 at the 17 Nov open): 17 Nov 99194, 18 Nov 98891, 19 Nov 96950, 20 Nov 93421, 23 Nov 97820, 24 Nov 97344, 25 Nov 97063, 27 Nov 98636.
- `return` "+2.0%", `spyReturn` "−1.4%", `sharpe` "3.44", `largestDrop` "−1.4%".
- Slide 8 headline: "The account ended up 2.0% while the S&P 500 fell 1.4%, but most of the gain was never locked in." Under the chart show "Account value at the close: $101,942 (+1.9%)" and "Locked in (realised): about −$242", and the line "Nine holdings were never sold. See slide 12." Footnote: "Sharpe ratio over 8 days is unstable."
- `wwdExit`: "Never sold: final sell-off failed. Worth $352.03 at the close, +$587 on paper."
- `trades`:
  - ACM: keep as is.
  - WWD: why "Earnings beat 13%, rated explained up"; result "Not sold; +$587 on paper"; tone gain; lesson "The trade worked; the exit didn't run."
  - PDD: why "Earnings beat, rated explained up"; result "Not sold; +$230 on paper"; tone gain; lesson "A later bounce trade on PDD was blocked by the weak-market rule."
  - NVDA: why "Jumped 24% when its CEO was reinstated; rated explained up"; result "Not sold; −$123 on paper"; tone loss; lesson "Bought late in the window, with little time to work."
- Slide 10: `verdictHeadline` "Too few graded trades to tell whether reading the news helped." Replace the three bars with two plain facts from `docs/results.md`: "The analyst's up/down calls were right 52% of the time (50 graded calls)" and "Its confidence scores were not well calibrated (Brier 0.29; target was below 0.25)". Footer: "We could not score the follow-the-move and fade-the-move comparison: the matched records were missing."
- `credits`: "1,748 credits over 158 cloud sessions".
- Slide 12 now lists six stops (see "Final-day failure" above).

Read `docs/post-mortem.md` before writing slide 12's sixth point and the slide 8 headline, so wording matches it.

Read `docs/results.md` and the generated results files in `docs/`. Fill every null in `deck/data.json`: full daily equity and SPY series 17-27 Nov, return, SPY return, Sharpe, largest drop, credits, WWD exit, the trades table (WWD, PDD, NVDA rows plus ACM), and the follow/fade comparison with `verdictHeadline`. Write the slide 8 and slide 10 headlines as plain sentences from the actual numbers, even if the result is a loss or "too few trades to tell". Also on slide 5, align the five steps with the left margin and spread them across the full width so each step wraps less. Do not change any other slide text. Run `python deck/sync_data.py`, re-run the checks above, then commit "Fill deck results (Stage 2)". Do not push.

---

## Stage 3 (28 Nov): match the judging criteria

The judges score: risk-adjusted return 25%, Qoder and Cloud Agent use 30%, strategy and risk design 30%, reusability and documentation 15%. Stage 3 adds five slides and changes three. Keep style C exactly (warm paper, Georgia headlines, Segoe UI body, pixel ducks, thin rules). Plain words, no buzzwords, no exclamation marks. Every fact below is checked against the repo; do not add others.

### New order (21 slides)

| New # | Slide | Source |
|---|---|---|
| 1-4 | Title, The question, Our bet, The desk | unchanged |
| 5 | **NEW: One run, start to finish** | below |
| 6 | **NEW: See it run** (30-second video) | below |
| 7 | A trade, start to finish (WWD) | old 5 |
| 8 | Where the money sits | old 6 |
| 9 | Saying no | old 7, one row changed |
| 10 | **NEW: How we'd know we're wrong** | below |
| 11 | Results | old 8, two changes |
| 12-16 | Every trade, Did the news help, Day one, The brakes, Lessons | old 9-13 |
| 17 | How Qoder ran it | old 14 |
| 18 | **NEW: 15 reusable skills** | below |
| 19 | **NEW: One skill up close, and the agent templates** | below |
| 20-21 | Reuse it, Honest summary | old 15-16 |

Slide numbers ("n / 21") and notes must follow the new order. Add a speaker note (1-3 sentences) for each new slide.

### Slide 5 (new): One run, start to finish
- Kicker "HOW THE AGENTS WORK TOGETHER". Headline: "Every 30 minutes, one run goes from schedule to order to record."
- A left-to-right flow of six steps. Agent steps show their duck; code steps show a small "Python" label in the accent colour, so the split between AI and code is visible at a glance:
  1. **Qoder schedule**: starts a cloud session (morning, then every 30 minutes).
  2. **Coordinator** (duck): restores the ledger and runs each step in order.
  3. **Analyst** (duck): reads the news, rates each unusual move, fetches fresh quotes.
  4. **Python**: checks the rating, sizes the trade, applies the risk rules, writes the order ticket.
  5. **Executor** (duck): sends exactly that paper order to moomoo.
  6. **Python**: matches the fill to the books and saves the ledger.
- Below the flow, a band "After the close": "The Auditor (duck) checks the books. Code writes the summary. It is posted to Slack." Show `deck/img/slack-close.png` (already added: the real 19 Nov Slack post) at a readable size beside that text.
- Footer: "Watcher runs skip the news step and look after open positions. The Auditor has no order tools."

### Slide 6 (new): See it run
- Kicker "SEE IT RUN". Headline: "The desk in 30 seconds."
- A `<video>` filling most of the slide: `src="video/moowoo-desk-30s.mp4"`, `poster="video/poster.jpg"`, `controls`, `preload="metadata"`, no autoplay, no loop. Both files will be in `deck/video/`; if they are missing when you build, still write the markup and leave a thin-rule placeholder box of the same size.
- Pressing Space or clicking the video plays and pauses it; arrow keys still change slides. In print mode show the poster image only.

### Slide 9 (changed): Saying no
- Row "The account is down 2%, 4% or 6%": add "from its peak" to the left cell, and change the right cell to "Smaller trades, then sells only, then sell everything (the kill switch)."

### Slide 10 (new): How we'd know we're wrong
- Kicker "WHEN TO STOP". Headline: "We wrote down in advance what would prove the idea wrong."
- Left column "The idea fails if":
  - "After 15 closed news trades, the analyst's picks do worse than simply following every move, or simply fading every move."
  - "Then news trades stop for the rest of the window, money moves to the steady funds, and we report the idea as failed."
  - Muted line: "We closed only one news trade, so this test never ran."
- Right column "Hard limits on every order":
  - "At most 20% of the account in one stock"
  - "At most 60% in news trades, 40% when the market is weak"
  - "At least 10% kept in cash"
  - "Price spread at most 0.5%; prices no older than 60 seconds"
  - "Missing data can never approve a buy"
  - "Real-money order tools are switched off for every agent"

### Slide 11 (changed): Results
- Next to "−1.4% Largest drop" add, in muted text: "S&P 500: −6.6%". (Both measured from the 17 Nov start to the lowest close: account 98,562, S&P 500 rebased 93,421.)
- Change "Nine holdings were never sold. See slide 12." to "See slide 15."

### Slide 18 (new): 15 reusable skills
- Kicker "REUSABLE SKILLS". Headline: "15 skills: tested steps anyone can copy."
- Four columns, one plain line per skill (skill name in small mono, line in body text):
  - **Finding the trade**
    - explained-move: finds stocks moving far more than usual
    - news-vs-noise-classifier: one analyst rating: is there news behind the move?
    - price-action-setup: scores the chart pattern; logged only, never used for sizing
    - market-regime: blocks bounce trades when the S&P 500 is weak
  - **Sizing and guarding**
    - core-satellite-allocator: splits money between steady funds and news trades
    - risk-desk: approves, resizes or vetoes every proposed order
    - order-ticket-dispatch-check: rechecks price and limits just before sending
  - **Keeping the books honest**
    - broker-input-validation: checks broker data before it is trusted
    - reconciliation-and-halts: matches fills to the books; stops on a mismatch
    - hash-chained-event-log: a tamper-evident record of every decision
    - ledger-persistence-and-locks: lets short cloud runs share one ledger safely
    - pre-registration-and-rule-ledger: freezes rules before trading; logs every change
  - **Running and reporting**
    - qoder-cloud-deploy: previews and applies agent and schedule versions
    - dashboard-feed-publish: publishes a public view with private data removed
    - daily-audit-report: after-close numbers, and what is missing
- Footer (muted): "Each skill is a written procedure in skills/ that points to tested code. They are not loaded into the agents automatically."

### Slide 19 (new): One skill up close, and the agent templates
- Kicker "REUSE IT". Headline: "One skill up close: never trust broker data unchecked."
- Left, three short rows:
  - **Why it exists**: "On 18 Nov the coordinator dropped a field while copying a broker record, and the desk stopped."
  - **What it does**: "Keeps only the fields we need, checks them, and saves the file in one step. A bad reply is fetched again up to twice, then the run stops with a reason."
  - **Why it is reusable**: "Any agent that reads a broker or an API can follow the same steps: never copy a summary, never guess a field name."
- Right, "Agent templates":
  - "Each agent is two files: agent.json (model and tools) and system.md (its instructions), in agents/."
  - "permissions.json switches off real-money order tools for every agent."
  - "Only the executor can send paper orders. The auditor can only read."
  - Small duck row: coordinator, analyst, executor.

### Checks, then commit
Run `python deck/sync_data.py`. At 1920x1080 confirm nothing overlaps or is cut off on slides 5, 6, 10, 18 and 19 (slide 18 has the most text: if it does not fit at body size, reduce the skill lines to a smaller size rather than cutting skills). Confirm the counter shows "n / 21", the print/PDF output is 21 pages, and arrow keys, Home, End, `p` and `#n` links still work. Commit "Deck Stage 3: judging criteria slides". Do not push.
