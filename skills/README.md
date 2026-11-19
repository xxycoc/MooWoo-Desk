# Reusable MooWoo Desk skills

These procedures package existing repository behavior. They are not installed
Qoder resources: the agent definitions still declare `skills: []`. Each skill
names its real inputs, outputs and limits. Read the linked code and the latest
pre-registration addenda before using a procedure in another experiment.

All paths in a skill are relative to the repository root. Strategy thresholds
come from `moowoo/config.py` plus registered changes, not from the skill text.
Run offline tests before changing a procedure. These instructions do not grant
broker, deployment, publication or account access.

## Strategy

| Skill | Use when | Main implementation |
| --- | --- | --- |
| [explained-move](explained-move/SKILL.md) | Selecting and interpreting abnormal daily movers | `moowoo/screener.py`, `moowoo/indicators.py` |
| [news-vs-noise-classifier](news-vs-noise-classifier/SKILL.md) | Producing or ingesting one analyst rating | `agents/analyst/system.md`, `scripts/ingest_ratings.py` |
| [price-action-setup](price-action-setup/SKILL.md) | Calculating a log-only price-action score | `moowoo/setup_score.py` |
| [core-satellite-allocator](core-satellite-allocator/SKILL.md) | Proposing core rebalances and satellite entries | `moowoo/core.py`, `moowoo/sizing.py` |
| [market-regime](market-regime/SKILL.md) | Applying the SPY entry-regime filter | `moowoo/desk_data.py`, `moowoo/risk.py` |
| [risk-desk](risk-desk/SKILL.md) | Approving, resizing or vetoing proposals | `moowoo/risk.py`, `moowoo/portfolio.py` |

## Infrastructure

| Skill | Use when | Main implementation |
| --- | --- | --- |
| [hash-chained-event-log](hash-chained-event-log/SKILL.md) | Writing or verifying decision evidence | `moowoo/ledger.py`, `scripts/verify_ledger.py` |
| [ledger-persistence-and-locks](ledger-persistence-and-locks/SKILL.md) | Coordinating ephemeral scheduled workers | `moowoo/persistence.py`, `moowoo/runlock.py` |
| [pre-registration-and-rule-ledger](pre-registration-and-rule-ledger/SKILL.md) | Registering an experiment or an explicit deviation | `scripts/freeze_config.py`, `scripts/hash_prompts.py`, `moowoo/rules.py` |
| [order-ticket-dispatch-check](order-ticket-dispatch-check/SKILL.md) | Handing a prepared paper ticket to the executor | `scripts/dispatch_check.py`, `moowoo/execution.py` |
| [broker-input-validation](broker-input-validation/SKILL.md) | Saving broker snapshots without copy errors | `scripts/check_broker_input.py`, `moowoo/broker_fields.py` |
| [reconciliation-and-halts](reconciliation-and-halts/SKILL.md) | Resolving fills, reservations or mismatched books | `scripts/reconcile.py`, `moowoo/execution.py` |
| [qoder-cloud-deploy](qoder-cloud-deploy/SKILL.md) | Previewing or applying versioned cloud resources | `scripts/qca_deploy.py` |
| [dashboard-feed-publish](dashboard-feed-publish/SKILL.md) | Exporting a public view without private runtime data | `scripts/export_dashboard.py`, `scripts/publish_feed.py` |
| [daily-audit-report](daily-audit-report/SKILL.md) | Producing after-close metrics and explicit gaps | `scripts/gather_audit_inputs.py`, `scripts/audit_report.py` |

For the active architecture, schedules and limitations see the
[main README](../README.md) and [Qoder usage guide](../docs/qoder-usage.md).

