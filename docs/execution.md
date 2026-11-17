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
   NOT assumed: collect new status/snapshots and reconcile again after cancelling.
8. The independent auditor consumes the reconstructed books, verified JSONL and
   cancellation results, then writes its report. No report delivery is claimed here.

Every invocation is one tick, not a daemon. The scheduler owns the 30-minute
cadence, holiday/early-close calendar, fresh snapshot acquisition and exclusive
ownership of the account. The watcher validates the supplied regular-session
window and quote age, but does not independently fetch an exchange calendar.

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
          "order_type":1,"order_side":1,"qty":50,"price":100,
          "order_trade_time_type":0,"text":"2026-11-17-us:AAA"},
  "status":"placed","response":{"order_id":"synthetic-order-1","status":"SUBMITTED"}}]
```

The adapter includes `order_trade_time_type=0` explicitly. Confirm that enum's
broker session semantics before real use; the known tool schema lists 0/1/2 but
does not establish their meanings. All tickets remain limit orders. Every request
field, missing field or extra field is verified; mismatches halt immediately.
Optional broker-echoed `args`, when supplied, must also match exactly.
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

## Field mappings

Each tool has one table in `moowoo/broker_fields.py`. Missing required fields,
invalid numbers, unknown status, foreign routing, duplicate rows or incomplete
history pagination raise rather than guess. Optional fields may be absent.

| Tool/table | Required broker fields | Optional fields | Evidence |
| --- | --- | --- | --- |
| `sim_trade_account_list` / `ACCOUNT_LIST` | `account_id`, `market_id`, `account_type`, `account_title` | `broker_id`, `intra_account_id` | Row names confirmed; root-list envelope provisional |
| `sim_trade_cash_info` / `CASH_INFO` | `cash`, `equity` | `acc_id`, `market` | All provisional; root object |
| `sim_trade_position_list` / `POSITION_LIST` | `symbol`, `qty`, `avg_cost`, `market_price` | `text` (entry decision), `acc_id`, `market` | All provisional; rows under `data` |
| `sim_trade_history_order_list` / `ORDER_HISTORY` | `order_id`, `symbol`, `text`, `order_side`, `qty`, `price`, `filled_qty`, `avg_price`, `status` | `acc_id`, `market`; root `next_key` | All response fields provisional; rows under `data` |
| `sim_trade_input_order` / `INPUT_ORDER` | `order_id` | `status`, `reason`, `args` | All response fields provisional; root object |

History status strings `SUBMITTED`, `PARTIAL`, `FILLED`, `CANCELLED`, `REJECTED`,
the `US.` response-symbol prefix, numeric side encoding and whole-share quantity
semantics need real response confirmation. Nonempty `next_key` rejects an incomplete
snapshot: the agent must combine all pages first. A zero-fill order still requires
explicit `filled_qty=0`, `avg_price=0` and status. All `fixtures/broker/provisional_*.json`
are synthetic examples, not captures. Cash is assumed to be total ledger cash,
not buying power or cash net of pending reservations. Verify fee treatment and
average-cost semantics before launch. Optional routing absent means Python cannot
prove snapshot account provenance; the agent must retain its request context.

## Reconciliation and locking

Order-status fills are cumulative. Apply only quantity/notional/fee deltas since
`state.execution.fills[orderId]`. The USD 0.99 fee is charged once per filled order;
sell levy is cumulative USD 0.000166 per sold share, capped at USD 8.30. No fill
means no fee. Partial quantity leaves the remainder reserved until terminal status.
The competition's volume-times-20 rule can produce partial fills; code does not
predict them. Only returned order status establishes the filled quantity.

Independent books take quantity, average cost and cash from broker snapshots.
Strategy fields carry over only on matching ticker and entry decision ID. When
position text is absent, a unique matching filled-buy decision in history is required.
Multiple buy identities for the same ticker are ambiguous, not resolved by row order. Unknown
strategy identity fails closed. Quantity must match exactly; aggregate position
cost and cash each tolerate USD 1 after fees. Broker equity must also agree with
cash plus marked positions within USD 1. Unexplained differences latch a halt and
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
