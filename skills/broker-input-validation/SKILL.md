---
name: broker-input-validation
description: Use when saving Moomoo account, cash, position or order-history responses for a deterministic session phase.
---

# Broker input validation

## Inputs

The actual broker response, expected snapshot kind and private run input folder.
Read `scripts/check_broker_input.py`, `moowoo/broker_fields.py`,
`moowoo/broker.py` and the current coordinator/auditor prompt.

## Procedure

1. Obtain snapshots through the role's allowed Moomoo read tools. Keep account routing private and verify paper-account type, market and challenge title.
2. Pipe the response into `scripts/check_broker_input.py` with the snapshot kind/output arguments from its CLI. It trims to required fields, validates and saves atomically. Never copy a conversational summary as a snapshot.
3. Preserve actual field names: position cost/current price are `cost_price` and `cur_price`; quantity is `qty`. Follow the parser for account, cash and history fields instead of guessing aliases.
4. Save all history pages with their cursors; use the script's `--assemble <inputs>` mode before reconciliation. A partial page is not complete account history.
5. On invalid replacement the script removes the stale previous file. Re-fetch at most twice after the initial failure, then abort the run with a recorded reason.
6. Run preflight and reconciliation only with validated inputs. Missing/malformed input aborts this run; genuine broker/book disagreement remains a persistent-halt condition.

## Outputs

Minimal validated private input JSON and assembled history for
`scripts/run_session.py` and `scripts/reconcile.py`, or an explicit failure with
no stale file masquerading as fresh data.

## Limits

Trimming is not permission to publish snapshots: allowed private fields include
account/order identifiers. Never print credentials or place raw payloads in the
public feed. Do not repair missing fields by invention or suppress true mismatches.
