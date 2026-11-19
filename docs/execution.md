# Offline execution and reconciliation

Python never calls Moomoo. Agents fetch snapshots, request human approval, call
MCP, and return JSON. All examples use the existing `.venv/Scripts/python`.
No synthetic fixture establishes compatibility with real order responses.

## Session sequence

1. Load `MOOMOO_ACCOUNT_ID` and `MOOMOO_MARKET=100` into the process environment
   from the private, gitignored `.env`. Scripts do not print or commit the file.
   Fetch `sim_trade_account_list` with no parameters and save its rows locally.
2. Run preflight. It checks the unique configured account's `account_type=2`,
   `market_id=100`, title containing `Qoder`, config and universe hashes, current
   prompt hash against the latest dated addendum, and halted state/log.
3. Plan using `plan_session.py` and its existing ratings, quotes and completed bars.
4. Prepare tickets. Give the emitted `orders` list to the executor. It contains
   the exact tool name, arguments, decision ID and attempt number.
5. Executor waits for human approval for each paper order, places only approved
   arguments, then returns receipt envelopes. Record these before further work.
6. Invoke the watcher every 30 minutes with fresh quotes and completed bars.
   Submit its exit tickets through the same preflight/prepare/record sequence.
7. At close, fetch complete order history, positions and cash. Reconcile each
   ticket batch against its own run log, updating the shared saved state.
   Reconcile fills before starting another batch. These single-manifest commands
   cannot attribute simultaneous unreconciled fills from other run logs; they halt
   on that difference instead of treating it as cash or an unexplained holding.
   Give emitted cancel arguments to the executor for approval. Cancellation is
   NOT assumed: record a successful cancel receipt, collect fresh snapshots,
   and reconcile again after cancelling.
8. The independent auditor consumes the reconstructed books, verified JSONL and
   cancellation results, then writes its report. No report delivery is claimed here.

Every invocation is one tick, not a daemon. The scheduler owns the 30-minute
cadence, holiday/early-close calendar, fresh snapshot acquisition and exclusive
ownership of the account. The watcher validates the supplied regular-session
window and quote age, but does not independently fetch an exchange calendar.

## Dispatch quote refresh

Before each broker handoff, `scripts/dispatch_check.py` reads
`inputs/<runId>/quotes-raw-<TICKER>.json`. A stale quote or an unreadable quote
file (missing file, malformed JSON, invalid envelope/quote fields, or anything
other than exactly one row) gets one refresh. The first failure logs
`quote_refresh` and returns `ok:false`, `skipped:false`, `retryable:true` and
`quoteAttempt:1`. For unreadable input, the reason is
`unreadable quote file; fetch one fresh quote and rewrite it`.
The coordinator must fetch one new single-symbol quote, rewrite the file and
repeat the same dispatch check. Stale and unreadable failures share this budget:
a second failure skips the ticket. Quote refreshes do not increment the broker
placement attempt or change the prepared ticket.

If the file becomes unreadable or the quote expires during the authorization
checkpoint, the checker logs `dispatch_withheld` before `quote_refresh`.
Never retry a returned `ok:true` authorization or a broker handoff.
Valid quotes that fail the limit-price, spread, symbol, future-timestamp or
core cash/limit checks remain immediate, non-retryable skips; when existing cash
and core room cannot cover reserved buys, reconciled core sells are still required.

## Commands and files

| Script | Reads | Writes |
| --- | --- | --- |
| `preflight.py --accounts accounts.json --state state.json --log ledger/2026-11-17-us.jsonl` | Account rows, state, frozen config, universe, local preregistration and prompts | `run_started` or `halt`; nonzero on halt |
| `plan_session.py` | Existing market/ratings inputs and state | Ticket manifest, reserved state, intents and risk verdicts |
| `execute_tickets.py prepare --tickets tickets/2026-11-17-us.json --log ledger/2026-11-17-us.jsonl` | Immutable tickets, verified log, environment routing | Exact MCP arguments on stdout; durable prepared-attempt notes |
| `execute_tickets.py record --tickets tickets/2026-11-17-us.json --responses responses.json --log ledger/2026-11-17-us.jsonl` | Executor receipt JSON | `order_submitted`, failure/skip notes, or `halt` |
| `watch.py --state state.json --quotes quotes.json --bars-asof 2026-11-16 --log ledger/2026-11-17-watch-1500.jsonl` | State, timestamped quotes, cached bars | Exit ticket manifest, `stop_hit`, risk verdict, tighter stops and reservations |
| `reconcile.py --history history.json --positions positions.json --cash cash.json --tickets tickets/2026-11-17-us.json --state state.json --log ledger/2026-11-17-us.jsonl` | Broker snapshots, tickets, saved books and receipts | Cumulative `fill` events, saved state/checkpoints, cancel arguments on stdout, or `halt` with diff |

Watcher bars default to `.cache/desk/bars.json`; override with `--bars`.
Ticket output defaults to `tickets/`; override with `--tickets-dir`.
Run identity is the log filename stem and must match the ticket manifest.
The v0 contract permits only `runId:TICKER`. A later same-ticker exit therefore
needs a distinct watcher run/log, not a second order under an entry's ID. Preflight
that log before preparation. Never run different logs against the same state
concurrently: the account scheduler must serialize those operations.

Pending tickets reserve capacity only. A pending remainder retains the original
ticket hash as provenance but is not itself a new executable ticket. Always use
the original immutable manifest for record and reconciliation.

## Registration and approval

The owner must commit a dated addendum before trading. Example format (replace
the placeholder with the exact output of `scripts/hash_prompts.py`):

```text
## Addendum 2026-11-17
promptVersion=<64 lowercase hex characters>
```

Preflight reads the working-tree document. The operator must ensure its addendum
is committed; it does not certify Git provenance. Missing addendum reports exactly
`prompts not pre-registered`. This implementation deliberately does not register
its own prompts. Changing prompts or default permissions invalidates the old hash.

Only the executor has enabled simulated input/cancel/modify tools, all defaulting
to `always_ask`. Other agents deny them; real-money and crypto order tools remain
denied everywhere. `qca_deploy.py --executor-approval ask|allow` defaults to ask.
Dry-run allow only builds a manifest. Applying allow requires `--approval-log`
whose latest non-drill `rule_change` with `ruleId=executor_approval` has `after=allow`.
The manifest and executor metadata record the override separately from the source
`promptVersion`, which hashes the checked-in default policy, not deployed overrides.
Neither dry run nor this implementation authorizes a deployment.

## Executor receipt format

`responses.json` is a list of envelopes written by the executor, not a claimed
raw broker response format. Copy `decisionId`, `attempt` and `args` verbatim from
prepare output. Do not commit receipts because `args` contains the account ID.

```json
[{"decisionId":"2026-11-17-us:AAA","attempt":1,
  "args":{"acc_id":"synthetic-paper-account","market":100,"symbol":"US.AAA",
          "order_type":1,"order_side":1,"qty":"50","price":"100.00",
          "order_trade_time_type":1,"text":"2026-11-17-us:AAA"},
  "status":"placed","response":{"ret_code":0,"ret_msg":"success","data":{"order_id":"3164623"}}}]
```

The adapter sends `order_trade_time_type=1` (intraday only), as preregistered.
The schema defines 0 as not set and 2 as including pre/after-hours.
All tickets remain limit orders. Every request
field, missing field or extra field is verified; mismatches halt immediately.
Qty and price compare numerically using Decimal; all other arguments compare
exactly, including type. Optional broker-echoed `args` follow the same checks.
Never infer a fill from placement acceptance.

Failures use `status` of `rejected`, `failed`, `timeout` or `approval_expired`
and a nonempty `reason`. Unknown status or malformed receipt halts. Approval
expiry is a session skip, not a retry. Rejected placement may retry once.
Failed/timeout placement remains blocked until complete history confirms absence;
resubmit its receipt with `absenceConfirmed:true` only after that check. This
flag is the executor's evidence assertion, not an independent Python broker query.
After two failed attempts the ticker is skipped for the run. No third attempt.
Reconciliation releases reservations for terminal skips without submissions while
retaining their decision IDs, so approval expiry cannot strand reserved cash.
Prepared-but-unacknowledged attempts cannot be prepared again. A lost stdout
handoff therefore needs explicit history/approval resolution, not blind replay.
The `mcp_timeout` drill exercises this policy without submitting or reserving orders.

## Field mappings and evidence (17 November 2026)

Missing required fields, invalid decimals, unknown sides, foreign account routing,
duplicate order IDs and incomplete pagination fail closed. Unknown integer status
codes do not determine fills or halt reconciliation. The two `real_sim_trade_*.json`
captures use `<ORDINARY_PAPER_ACC>` and prove no competition-account eligibility.

### Confirmed

- Placement request: `acc_id`, account `market=100`, `symbol="US.AAPL"`,
  `order_type=1`, buy `order_side=1`, string `qty` and `price`,
  `order_trade_time_type`, `text`. MooWoo emits integer quantity strings and
  exactly two price decimals. The capture used session type **2**; MooWoo sends
  **1**, so the sample is evidence, not a compliant ticket to replay.
- Placement response: integer `ret_code`, string `ret_msg`, `data.order_id`.
  Only ret_code 0 succeeds. Nonzero codes log ret_msg as placement failures and
  never create `order_submitted`, even if an executor labels the receipt placed.
- History request: `acc_id`, account `market=100`, microsecond `time_begin` and
  `time_end`, `page_size`. Response: `ret_code`, `ret_msg`, `data.orders`, and
  `pagination.has_more` / `pagination.next_key` either inside `data` or beside it.
  If both appear they must agree. Multi-page requests still require verification.
- Required history row fields: `order_id`, `symbol`, `text`, `side`, `qty`,
  `price`, `cum_qty`, `avg_fill_price`, `status`. Observed optional fields:
  `market`, `create_time`, `update_time`, `order_trade_time_type`, `order_type`,
  `time_in_force`. `aux_price` and `stock_name` are observed but unused.
- Symbol is unprefixed `AAPL`; the adapter normalizes either `AAPL` or `US.AAPL`.
  History `market=2` is internal and never compared to account market 100.
  Decimal strings parse numerically; microsecond timestamp strings parse to
  integer microseconds. Observed cum_qty="0" and avg_fill_price="0" are unfilled.
- Status 2 is labelled `accepted/resting (observed)`; status 5 was observed after
  cancellation and is labelled `cancelled (observed)`. These are display labels
  only. Fills derive solely from quantities: cum_qty=qty means full,
  0<cum_qty<qty means partial, cum_qty=0 means unfilled. Status cannot prove cancellation.
- Previously confirmed account row names: `account_id`, `market_id`, `account_type`,
  `account_title`, `broker_id`, `intra_account_id`.

- Cancel success is `{"ret_code":0,"ret_msg":"success","data":{"order_id":"..."}}`.
  The returned order ID must match the recorded submission and exact cancel args.
  A logged successful cancellation releases only the unfilled remainder.
- Cash response has `ret_code`, `ret_msg`, and object `data`. `balance` is free
  cash; `hold` is reserved cash including open-order fees; `total_asset` is equity.
  `long_mv`, `mv`, `short_mv` are observed market-value fields. Null
  `realized_profit` / `unrealized_profit` become zero. `max_power_long` is margin
  buying power, NOT cash or equity, and is never used by sizing or risk.
- Positions response has `data.positions` (observed empty list). The new scrubbed
  captures are `real_sim_trade_cancel_and_history.json` and
  `real_sim_trade_cash_and_positions.json`. These ordinary-paper probes do not
  prove competition-account behavior or nonempty position row semantics.

### Still provisional

- Account-list root-list envelope (`provisional_accounts.json`).
- Legacy offline fixtures retain normalized root `cash`/`equity` and a positions
  list under `data`; these are not claims about live envelopes.
- Nonempty rows under `data.positions`: `symbol`, `qty`, `cost_price`,
  `cur_price` (observed live 18 Nov), optional entry `text`, `acc_id`, `market` remain provisional,
  including average-cost and strategy-identity semantics.
- Filled/partial values and average-fill-price behavior, whole-share assumptions
  beyond the one-share capture (`provisional_history_filled.json`), and fees.
- Side 1 is observed buy; side 2 sell is the existing provisional mapping.
  No response status/side/time_in_force enum is documented. No meaning is assigned
  to time_in_force or unknown status codes.
- `provisional_cancel.json` is still synthetic but now follows the observed
  cancellation envelope. Already filled quantity and fees remain after cancel.
- Optional history `acc_id` and placement echo `status`, `reason`, `args` are not
  captured. Echo status never determines acceptance.
- Multi-page continuation is not captured. The executor must verify the actual
  continuation request schema and retain request context; no input parameter
  name is invented from the response's next_key.

`parse_history(first_response, fetch_page)` follows the exact `pagination.next_key`
while `has_more` is true, validates each page and rejects repeated cursors.
The offline CLI accepts `--history-pages pages.json`, an object keyed by requested
next_key, with subsequent response envelopes as values. Missing pages halt.
Terminal next_key="0" with has_more=false does not fetch another page. Python
makes no network calls. Keep account, market and time range identical across
requests. Missing optional routing means Python cannot prove account provenance.

Recorded order_id is the primary identity, so arbitrary broker text does not
replace the receipt's decisionId. Text decisionId is the fallback for history-backed
strategy identity without a local submission. A current-run text match without a
recorded submission fails closed until its receipt is recorded. Conflicting order
IDs are not silently reassigned.

Record cancellation through `execute_tickets.py record` with `decisionId`,
`tool="sim_trade_cancel_order"`, exact `args` containing `acc_id`, `market`,
`order_id`, and `response` containing `ret_code`, `ret_msg`, and a matching
`data.order_id`. A matching logged submission is required. Failure logs do not
release reservations. Reconcile fresh
history, positions and cash afterwards; a broker status alone never releases them.

## Reconciliation and locking

Order-status fills are cumulative. Apply only quantity/notional/fee deltas since
`state.execution.fills[orderId]`. The USD 0.99 fee is charged once per filled order;
sell levy is cumulative USD 0.000166 per sold share, capped at USD 8.30. No fill
means no fee. Partial quantity leaves the remainder reserved until logged cancellation succeeds.
The competition's volume-times-20 rule can produce partial fills; code does not
predict them. Only returned cumulative quantities establish fills. Zero fills emit no fill event.

Independent books take quantity, average cost and cash from broker snapshots.
Strategy fields carry over only on matching ticker and entry decision ID. When
position text is absent, a unique matching filled-buy decision in history is required.
Multiple buy identities for the same ticker are ambiguous, not resolved by row order. Unknown
strategy identity fails closed. Quantity must match exactly; aggregate position
cost and cash each tolerate USD 1 after fees. Broker equity must also agree with
free cash plus broker-reserved cash plus marked positions within USD 1.
`PortfolioState.cash` stays free cash; `brokerReserved` tracks hold. Pending-ticket
reservations subtract only the portion not already withheld by the broker, so
funds are neither double-reserved nor turned into margin buying power.
Unexplained differences latch a halt and
retain expected books/checkpoints, not overwrite them with unexplained holdings.

Events are appended before atomically replacing state. Replaying after a crash
reapplies deltas from the saved checkpoint but does not duplicate identical fill
events. Watcher approved tickets in the log recover reservations after interruption.
No fake exit order ID is invented: `stop_hit.exitOrderId` is empty until submission,
and `exitDecisionId` identifies its pending-approval ticket.

`EventLog` obtains `<log>.lock` with exclusive creation before verifying and
appending, then fsyncs the JSONL write and releases the lock. Default timeout is
five seconds with a clear error. Planner and execution scripts hold this lock
across their complete transaction. A process crash can leave a stale lock: never
remove it automatically. Confirm no writer is alive and inspect the log/state
before manually removing it. This is a local-filesystem lock, not a distributed
account lock across machines, logs, MCP calls or approval waits.
