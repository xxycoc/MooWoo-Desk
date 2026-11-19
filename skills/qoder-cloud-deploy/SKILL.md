---
name: qoder-cloud-deploy
description: Use when previewing, creating or updating the desk's Qoder Cloud Agent resources and separately approved schedules.
---

# Qoder cloud deploy

## Inputs

Committed source/prompt revision, private nonsecret bindings, full verified Moomoo
tool inventory and existing deployment receipts when updating. Read
`scripts/qca_deploy.py`, `agents/permissions.json` and `docs/qoder-usage.md`.
Applying requires privately supplied Qoder and ledger credentials; never echo them.

## Procedure

1. Run `scripts/qca_deploy.py` without `--apply` for a credential-free, network-free preview. Preview schedules separately with `--stage schedules`.
2. Resolve account, MCP, identity and source-revision bindings privately. Verify the official vault and every enabled/disabled tool. Pin the same code revision as the registered prompt content.
3. After explicit authorization, use `--settings <private-bindings.json> --apply --stage resources` to create the environment, four agent resources and two templates. This does not start schedules.
4. For existing resources, add `--update` and retain the private receipt file. The builder reads current versions, updates in place and pins child references; it does not update schedules in that mode.
5. Apply the separately approved schedule stage using the saved receipts. The coordinator template runs morning/watch; auditor runs independently. Review all six cron expressions and the trading-window stop time.
6. Keep executor approval at the default `ask` unless the exact logged AUTONOMY-01 addendum authorizes `allow`, supplied with the approval-log option. Verify effective cloud permissions and one real paper-session path before claiming deployment success.

## Outputs

A dry-run manifest or private apply receipts with resource identities/versions.
The environment startup clones pinned source, installs dependencies, runs tests
and checks the prompt hash. Use `scripts/qoder_usage.py` separately for aggregate
credit reporting when authorized.

## Limits

Applying changes external resources; preview is not deployment. The existing
deployer may load private `.env` credentials on apply; the usage script is
environment-only. Local `skills/` procedures are not automatically uploaded or
bound, and no skill resource IDs should be invented. Missing Slack pairing means
no delivery sink, not a successfully delivered audit.
