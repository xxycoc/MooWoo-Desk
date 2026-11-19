---
name: ledger-persistence-and-locks
description: Use when running scheduled workers against the shared private ledger without concurrent writers or lost ephemeral state.
---

# Ledger persistence and locks

## Inputs

A private runtime Git checkout, authorized ledger credentials, current time and
run kind (`morning`, `watch`, `audit`). Implementation:
`moowoo/persistence.py::LedgerStore`, `moowoo/runlock.py` and
`scripts/run_session.py`. Never expose credentials or account context.

## Procedure

1. Start through `scripts/run_session.py --kind <kind> --phase start --dir <runtime>`. It restores and verifies the private `ledger` branch and acquires an account-wide lease by a non-force push.
2. If acquisition loses a race, skip the run. Do not rebase a losing acquisition into a second winner.
3. Retain the returned holder and require ownership before further phase or order work. Leases last 45 minutes; renew before expiry, up to 120 minutes from acquisition.
4. Persist phase checkpoints with `release=False`; keep prepared attempts durable before executor handoff. Keep all `.jsonl` runtime files valid event logs, with raw replies in `.json` or `.txt` instead.
5. Finish or abort through the phase runner. A successful final save includes state/evidence and releases the lease. Inspect the returned save status rather than assuming a commit reached the remote.
6. If saving fails, preserve local files and the remote lock state. Resolve ownership/conflicts before continuing; never force push or erase evidence.

## Outputs

Private persisted logs, state, tickets, receipts and handoffs, plus checkpoint
and lease evidence. `scripts/persist_ledger.py` provides lower-level restore/save
operations; use the phase runner for trading orchestration.

## Limits

The private ledger repository is separate from the public source and feed.
Git leases cannot fence a broker request already in flight. Expiry or ownership
loss stops further work; it is not authority to repeat an uncertain order.
