---
name: daily-audit-report
description: Use after the market close to grade matured calls and produce an honest daily desk report with missing-data reasons.
---

# Daily audit report

## Inputs

Owned audit session, reconciled private state/logs, validated account snapshots
and completed daily bars. Read `agents/auditor/system.md`,
`scripts/gather_audit_inputs.py`, `scripts/audit_report.py`, `moowoo/audit.py`,
`moowoo/outcomes.py` and `moowoo/hypotheses.py`.

## Procedure

1. Start the separate auditor run after the actual calendar close. It is not a coordinator child and cannot place orders.
2. Validate and reconcile broker snapshots, then gather completed bars with `scripts/gather_audit_inputs.py`. Include held, pending, traded and rated symbols, SPY and the five core ETFs; retain the coverage report.
3. Grade only matured calls using the `grade_calls` phase and evaluate available hypotheses with `score_hypotheses`. Do not count unobserved horizons as failures or fabricate prices.
4. Finish through `scripts/run_session.py --kind audit --phase finish`. The report writer preserves computable metrics, uses null with reasons for gaps, writes report artifacts and appends reflection evidence. It does not append a full `daily_report` event when the required numeric metrics are unavailable.
5. Include P&L, risk, fills, skips/vetoes and the reflection on surprises, changes and agent behavior only where supported. Keep model credit gaps unavailable; aggregate Qoder usage is a separate measurement.
6. Persist the result before relying on the optional paired Slack schedule sink. Without a delivery receipt, report generation is not proof of delivery.

## Outputs

`<runtime>/inputs/<run>/report.json`, `report.md`, dated JSON under
`<runtime>/reports/`, grading/hypothesis artifacts and log evidence.

## Limits

Missing report metrics cause report-only gaps/reflections, not a portfolio halt.
True reconciliation failures still halt. A short-window Sharpe/Sortino is
descriptive; the current SPY-open proxy is not the exact pre-registered benchmark.
Missing full-universe coverage, baseline anchors or paired intervals must remain
explicit. No claim of live audit success follows from passing offline tests.
