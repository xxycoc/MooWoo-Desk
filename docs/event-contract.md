# MooWoo Desk event contract, v0

One event occupies one canonical UTF-8 JSON line, terminated by LF (no BOM).
The JSONL log is the source of truth. SQLite is rebuilt from verified logs.
Core code uses the Python standard library only; no network or broker code exists.

## Common fields

| Field | Type | Rule |
| --- | --- | --- |
| `v` | integer | Exactly `0`; booleans are not integers. |
| `runId` | string | Nonempty; stable within a file. Normally `YYYY-MM-DD-us`. |
| `seq` | integer | Starts at 1 in each file; increments by 1 without gaps. |
| `ts` | string | ISO 8601 UTC ending in `Z`. |
| `decisionId` | string or null | `runId:TICKER` for a ticker or ETF; otherwise null or an explicit run-prefixed decision ID. |
| `type` | string | One of the 16 types below. |
| `drill` | boolean | Synthetic drill marker. A `drill` event requires `true`. Consumers must never route marked events to a broker. |
| `prevHash` | string | Previous event's stored `hash`, or 64 zero characters for seq 1. |
| `hash` | string | Lowercase SHA-256 hex digest of this event excluding its own `hash` field. |

## Required payloads

Extra JSON fields are permitted. Required fields, primitive types, listed enums,
and nested structures are validated. JSON numbers must be finite; NaN and infinity
are rejected. Numeric fields accept integers or floats, but never booleans.
Every `trdEnv` key, including those in extensions or nested objects, must equal
`"SIMULATE"`. Unknown event types and missing fields are errors.

| Type | Required payload fields and constraints |
| --- | --- |
| `run_started` | `universe`: string list; `equity`, `cash`: numbers; `tier`, `configHash`, `promptVersion`: strings; `trdEnv`: `SIMULATE`. |
| `screen` | `candidates`: list of objects with `ticker` (string), `movePct`, `z`, `rvol` (numbers), `earnings` (JSON value); `picked`: string list. |
| `rating` | `ticker`: string; `class`: `explained_up`, `explained_down`, `unexplained_up`, or `unexplained_down`; `confidence`: number 0–1; `tier`: `debate` or `quick`; `reason`, `transcriptRef`: strings; `newsCutoff`: UTC ISO 8601 with Z; `credits`: number; `setupScore`: integer 0–5. |
| `shadow` | `book`: `follow`, `fade`, or `equal_weight`; `ticker`, `side`: strings; `notional`, `price`: numbers. |
| `core_rebalance` | `etf`, `side`: strings; `targetWeight`, `actualWeight`, `qty`: numbers. |
| `order_intent` | `ticker`, `side`: strings; `sleeve`: `core` or `satellite`; `qty`, `limitPrice`, `notional`, `stop`: numbers; `sizing`: object. |
| `risk_verdict` | `ticker`: string; `verdict`: `approve`, `resize`, or `veto`; `rules`: string list; `firedRule`: string or null; `qtyAfter`: number. |
| `order_submitted` | `ticker`, `orderId`: strings; `qty`, `limitPrice`: numbers; `trdEnv`: `SIMULATE`. |
| `fill` | `ticker`, `orderId`, `status`: strings; `filledQty`, `avgPrice`: numbers; `source`: exactly `order_status`. |
| `stop_hit` | `ticker`, `exitOrderId`: strings; `entry`, `stop`: numbers. |
| `tier_changed` | `from`, `to`: strings; `drawdownPct`, `peakEquity`: numbers. |
| `halt` | `reason`: string; `scope`: `ticker`, `run`, or `all`. Include `ticker` when identifying a ticker halt. |
| `drill` | `name`: string; `expected`, `observed`: JSON values; `pass`: boolean; common `drill` must be true. |
| `rule_change` | `ruleId`, `effectiveFrom`: strings; `before`, `after`: JSON values; `triggerDecisionIds`: string list. |
| `reflection_note` | `prompt`, `text`: strings. |
| `daily_report` | `equity`, `pnlPct`, `baselinePct`, `brier`, `maxDrawdownPct`, `creditsUsed`: numbers; `shadowPct`: object with numeric `follow`, `fade`, `equal_weight`; `orders`, `vetoes`, `skips`: nonnegative integers. |

Unspecified business rules (such as side vocabulary, risk budgets, earnings
representation, and tier-transition thresholds) belong to later consumers.
Fixtures use `BUY`/`SELL`, fractional weights (0.10 = 10%), and percentage-point
returns (1.5 = 1.5%). They depict long entries and exits, never short orders.

## Canonical encoding and integrity

```python
canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
body = {key: value for key, value in event.items() if key != "hash"}
event["hash"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
event["prevHash"]  # Equals the preceding stored event["hash"].
```

Set `prevHash` before calculating `hash`. The helper also sets `allow_nan=False`
to enforce valid JSON. The hash covers all other common and payload fields,
including `prevHash` and any extensions. The full event, including its computed
hash, is then serialized canonically and followed by one LF byte.

`verify(path)` returns `VerifyResult(ok, count, bad_seq, reason)`. `count` is the
number of successfully verified events. On failure, `bad_seq` is the expected
1-based position of the first bad line, including when its declared seq is wrong.
Reasons are `bad hash`, `broken prevHash link`, `seq gap`, or a detailed
`validation error`. Success has null `bad_seq` and `reason`. An empty existing
log is valid with count 0; a missing file is an error. Duplicate JSON keys,
noncanonical whitespace, CRLF, blank lines, and unterminated final lines fail.

An edited payload fails at that event; a deleted interior event fails at the
first following position. Reordering also fails. Deleting a complete suffix,
replacing a log with an empty file, or recomputing the entire chain cannot be
detected by a self-contained hash chain. Detecting those changes requires a
separately trusted terminal hash/count or signature, outside this foundation.
This is integrity checking, not authentication.

## Append and projection APIs

```python
from moowoo.ledger import EventLog, build_sqlite, verify

log = EventLog("ledger/2026-11-19-us.jsonl")
# For other filenames: EventLog("events.jsonl", runId="2026-11-19-us")
event = log.append("reflection_note", {"prompt": "What changed?", "text": "Volume faded."})
result = verify(log.path)
build_sqlite([log.path], "ledger/ledger.sqlite")
```

`append(type, payload, decisionId=None, drill=False, ts=None)` supplies the common
fields and returns the full event. Payloads may not override common fields.
Ticker and ETF payloads automatically get `runId:TICKER`; explicitly supplied
IDs must match. `runId` comes from the filename, an explicit constructor argument,
or the first event of an existing nonstandard filename. Explicit IDs must match
existing contents. Default timestamps use current UTC; fixture timestamps never do.

Use one writer at a time per log. Every open and append verifies existing contents;
append performs one binary line write, flush, and fsync before returning. Writers
must be serialized by the caller; there is no cross-process locking. An interrupted
write may leave an incomplete tail, which is rejected without automatic repair.
There are no edit, delete, or truncate APIs. This guarantee does not extend to
arbitrary external filesystem edits or power-loss behavior of every filesystem.

`build_sqlite` verifies all inputs before creating a temporary database beside
the destination, commits and fsyncs it, then replaces the destination. A failure
preserves the existing database. It refuses an input log as output, no inputs,
or duplicate `(runId, seq)` keys across logs. Close existing readers before rebuilding.

| Table | Contents |
| --- | --- |
| `events` | Every event: `runId`, `seq`, `decisionId`, `ts`, `type`, `drill`, `hash`, `prevHash`, `raw` canonical full JSON. |
| `decisions` | One row per rating, including its required fields and full `raw` JSON. Repeated ratings for a decision remain separate rows. |
| `rule_changes` | Rule-change fields plus common identity and `raw`; `before`, `after`, `triggerDecisionIds` are JSON text. |
| `shadow_trades` | Shadow fields plus common identity and `raw`. |
| `agent_claims` | Empty: `decisionId`, `agent`, `claim`, `ts`. |
| `outcomes` | Empty: `decisionId`, `horizonEnd`, `correct`, `retVsSpy`, `maxFavorable`, `maxAdverse`. |
| `process_grades` | Empty: `decisionId`, `newsBeforeCutoff`, `rulesFollowed`, `wrongIfStated`, `reasoningMatchesClass`, `grade`. |
| `blame` | Empty: `decisionId`, `agent`, `cause`, `evidence`. |

Populated tables have primary key `(runId, seq)` and separate `decisionId` and
`seq` indexes. Empty annotation tables have `decisionId` indexes. SQLite booleans
use integers; later annotation tables are never invented or populated by the builder.
All events, including drills, remain in the projection, with their full raw JSON.

## Fixture examples

The following are actual payloads from the committed seed-7 fixture, with their
source run and seq. Common fields are omitted here for readability; the JSONL
files contain complete, independently verifiable events. Prices, reports, claims,
and returns are fictional illustrative values, not a financially reconciled replay.

### run_started

Source: `fixtures/2026-11-17-us.jsonl`, seq 1.

```json
{"cash":100000,"configHash":"a3eaf6abc332d3e7de719b87c99b379156f395667dbd2b24a0604e4c610195d0","equity":100000,"promptVersion":"fixture-v0","tier":"normal","trdEnv":"SIMULATE","universe":["AAPL","MSFT","NVDA","KO","USMV","XLP","XLV","IEF","GLD"]}
```

### screen

Source: `fixtures/2026-11-17-us.jsonl`, seq 7.

```json
{"candidates":[{"earnings":false,"movePct":1.7,"rvol":1.9,"ticker":"AAPL","z":2.1},{"earnings":false,"movePct":3.2,"rvol":2.4,"ticker":"NVDA","z":2.8},{"earnings":false,"movePct":-1.2,"rvol":1.4,"ticker":"KO","z":-1.8}],"picked":["AAPL","NVDA"]}
```

### rating

Source: `fixtures/2026-11-17-us.jsonl`, seq 8.

```json
{"class":"explained_up","confidence":0.618,"credits":3,"newsCutoff":"2026-11-17T14:29:00Z","reason":"Fictional fixture: volume supports the move; news evidence remains limited.","setupScore":4,"ticker":"AAPL","tier":"debate","transcriptRef":"fixture://2026-11-17-us/AAPL"}
```

### shadow

Source: `fixtures/2026-11-17-us.jsonl`, seq 10.

```json
{"book":"follow","notional":1000,"price":251.47,"side":"BUY","ticker":"AAPL"}
```

### core_rebalance

Source: `fixtures/2026-11-17-us.jsonl`, seq 2.

```json
{"actualWeight":0.0999,"etf":"USMV","qty":111,"side":"BUY","targetWeight":0.1}
```

### order_intent

Source: `fixtures/2026-11-17-us.jsonl`, seq 13.

```json
{"limitPrice":251.47,"notional":3017.64,"qty":12,"side":"BUY","sizing":{"method":"fixed_risk","riskBudget":100},"sleeve":"satellite","stop":245,"ticker":"AAPL"}
```

### risk_verdict

Source: `fixtures/2026-11-17-us.jsonl`, seq 14.

```json
{"firedRule":null,"qtyAfter":12,"rules":["long_only","cash","correlation"],"ticker":"AAPL","verdict":"approve"}
```

### order_submitted

Source: `fixtures/2026-11-17-us.jsonl`, seq 15.

```json
{"limitPrice":251.47,"orderId":"SIM-17-AAPL-BUY","qty":12,"ticker":"AAPL","trdEnv":"SIMULATE"}
```

### fill

Source: `fixtures/2026-11-17-us.jsonl`, seq 16.

```json
{"avgPrice":251.47,"filledQty":12,"orderId":"SIM-17-AAPL-BUY","source":"order_status","status":"FILLED","ticker":"AAPL"}
```

### stop_hit

Source: `fixtures/2026-11-18-us.jsonl`, seq 12.

```json
{"entry":251.47,"exitOrderId":"SIM-18-AAPL-STOP","stop":245,"ticker":"AAPL"}
```

### tier_changed

Source: `fixtures/2026-11-18-us.jsonl`, seq 9.

```json
{"drawdownPct":2.1,"from":"normal","peakEquity":100150,"to":"reduced"}
```

### halt

Source: `fixtures/2026-11-18-us.jsonl`, seq 19.

```json
{"reason":"Correlation veto remains active for this run.","scope":"ticker","ticker":"NVDA"}
```

### drill

Source: `fixtures/2026-11-17-us.jsonl`, seq 19.

```json
{"expected":"veto","name":"stale_price","observed":"veto","pass":true}
```

### rule_change

Source: `fixtures/2026-11-18-us.jsonl`, seq 20.

```json
{"after":{"maxPairCorrelation":0.8},"before":{"maxPairCorrelation":0.85},"effectiveFrom":"2026-11-19T14:30:00Z","ruleId":"correlation","triggerDecisionIds":["2026-11-17-us:NVDA"]}
```

### reflection_note

Source: `fixtures/2026-11-17-us.jsonl`, seq 20.

```json
{"prompt":"What would invalidate today's thesis?","text":"A volume reversal without supporting news would weaken it. Fixture only."}
```

### daily_report

Source: `fixtures/2026-11-17-us.jsonl`, seq 21.

```json
{"baselinePct":0.12,"brier":0.21,"creditsUsed":4,"equity":100150,"maxDrawdownPct":0.4,"orders":1,"pnlPct":0.15,"shadowPct":{"equal_weight":0.08,"fade":-0.1,"follow":0.2},"skips":1,"vetoes":1}
```
