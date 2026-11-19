---
name: hash-chained-event-log
description: Use when appending auditable desk events, checking log integrity or rebuilding the disposable SQLite projection.
---

# Hash-chained event log

## Inputs

Event payloads conforming to `moowoo/events.py` and `docs/event-contract.md`, a
run ID and an owned local JSONL path. Implementation: `moowoo/ledger.py`.

## Procedure

1. Open the file through `EventLog`, which verifies existing contents before use. Do not append raw JSON text manually.
2. Append schema-valid events through `EventLog.append`. Canonical UTF-8 JSON and LF bytes, sequence, previous hash and event hash form the file-local chain.
3. Keep one writer; the adjacent exclusive lock and fsync protect local writes. Use the separate remote run lease for cross-session coordination.
4. Verify the chain with `scripts/verify_ledger.py <log-or-glob>` before using it as evidence.
5. Rebuild the SQLite projection using `scripts/build_ledger.py --out <sqlite-path> <log-or-glob>`. Both CLI tools expand Windows literal wildcards.
6. For offline demonstrations, use `scripts/fixture_log.py --out <demo-dir> --game-out <demo-game-file> --seed 7` so the shipped fixture files are not overwritten.

## Outputs

Verified JSONL evidence and, optionally, a reproducible SQLite projection.
Fixture events are explicitly fictional/drill data, not live outcomes.

## Limits

Hashes provide integrity, not authentication. A trusted terminal checkpoint is
needed to detect whole-chain replacement or suffix removal. Do not repair
corrupted historical bytes silently. Raw private logs are not public exports;
use `scripts/export_dashboard.py` for a scrubbed view.

