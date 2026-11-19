---
name: dashboard-feed-publish
description: Use when exporting verified private ledger evidence into a scrubbed data-only dashboard feed after publication is authorized.
---

# Dashboard feed publish

## Inputs

A verified private ledger checkout and ref, or current runtime folder, plus a
dedicated output data directory. Read `scripts/export_dashboard.py`,
`scripts/publish_feed.py` and `dashboard/README.md`. Publishing requires authorized
`FEED_REPO_URL`, `FEED_BRANCH` and `GITHUB_FEED_TOKEN` supplied privately.

## Procedure

1. Export with `scripts/export_dashboard.py --ledger-repo <private-checkout> --ref <ledger-ref> --out <dedicated-data-dir>`, or use its mutually exclusive `--runtime <runtime>` source. The checkout mode does not fetch or change the source checkout.
2. Keep fixture inclusion opt-in. An optional `--until <UTC-cutoff>` limits the public snapshot; do not confuse this delayed view with current broker state.
3. Let the exporter verify event chains, project allowlisted fields, pseudonymize order IDs and scan the serialized artifacts. Never substitute a copy of the raw runtime.
4. Inspect the generated index/meta and scrubbed logs. The dedicated output directory is replaced/cleaned of obsolete export files, so never target a mixed-content or source folder.
5. Use `scripts/publish_feed.py` through the runtime completion path after publication approval. It stages only `data/` on the data-only branch, default `dashboard-feed`, and refuses main/master.
6. Check the returned publication result. If credentials are absent or publishing fails, preserve the authoritative private ledger and report the stale/unpublished public view.

## Outputs

Public `data/index.json`, `data/meta.json` and scrubbed event logs consumed by
`dashboard/src/data/load.ts`. The UI has no broker connection or embedded token.

## Limits

Scrubbed does not mean confidential: tickers, timing, prices, quantities, ratings
and permitted evidence text remain public. Do not publish private state, receipts,
locks, account context or raw transcripts. Feed publication does not deploy a new
dashboard build, and a deployment does not prove that the feed is fresh.
