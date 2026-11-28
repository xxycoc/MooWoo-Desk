# MooWoo Desk agent handbook

## 1. Binding rules

PREREGISTRATION.md is binding. Paper trading only, US stocks and ETFs, long only.
No first live order until the owner commits the dated promptVersion addendum.
LLMs do not size positions or place discretionary orders. Code issues tickets.
Never edit frozen configuration or bypass permissions. Missing safety-critical
inputs halt; log optional evidence gaps, with unavailable cost credits null.

## 2. Deployed agents at the end of the window

Retrieved from the Qoder Cloud Agents API at 2026-11-28 (UTC), after all schedules were
paused. Agent IDs are masked. Source revision `7a0e86f`, promptVersion
`000293a43af6094844f8d79c1856eee7072af3a37607b49f9da96e5371395075`.

| Agent | Agent ID | Cloud version | Model | Moomoo tools (always_allow) | Skills | Last updated (UTC) |
| --- | --- | ---: | --- | --- | --- | --- |
| coordinator | ***fbza | 37 | efficient | None | none | 2026-11-26 13:53 |
| analyst | ***q45l | 37 | ultimate | news_search, quote_market_snapshot, quote_stock_quote, quote_history_kline, quote_financials_earnings_price_move | none | 2026-11-26 13:53 |
| executor | ***xlsm | 37 | ultimate | sim_trade_input_order, sim_trade_cancel_order, sim_trade_modify_order, sim_trade_account_list, sim_trade_cash_info, sim_trade_position_list, sim_trade_history_order_list, sim_trade_max_buy_sell | none | 2026-11-26 13:53 |
| auditor | ***8zys | 37 | ultimate | sim_trade_account_list, sim_trade_cash_info, sim_trade_position_list, sim_trade_history_order_list | none | 2026-11-26 13:53 |

Built-in tools follow [agents/permissions.json](agents/permissions.json). Every real-money
and crypto tool is disabled. Executor order tools are always_allow under the logged
AUTONOMY-01 decision; no other agent can place, cancel or modify an order. Bull, bear,
manager and quick still exist as cloud resources but were retired from the session path by
Addendum 19 on 17 November and are never called. The coordinator moved to the cheaper
`efficient` model during the window; the table in section 2a is the original plan.

## 2a. Original agent registry (17 November plan)

All paths below are relative to this repository. Local revision is `agents-v1`.
Agent JSON embeds the prompt and permissions; deployment loads system.md as the
authoritative text. Models are planned IDs, pending account catalog verification.

| Agent | System prompt | Model | Built-in tools | Allowed Moomoo tools |
| --- | --- | --- | --- | --- |
| analyst | [agents/analyst/system.md](agents/analyst/system.md) | ultimate | None | news_search, quote_market_snapshot, quote_stock_quote, quote_history_kline, quote_financials_earnings_price_move |
| auditor | [agents/auditor/system.md](agents/auditor/system.md) | ultimate | Bash, Read, Write | sim_trade_account_list, sim_trade_cash_info, sim_trade_position_list, sim_trade_history_order_list |
| bear | [agents/bear/system.md](agents/bear/system.md) | ultimate | None | None |
| bull | [agents/bull/system.md](agents/bull/system.md) | ultimate | None | None |
| coordinator | [agents/coordinator/system.md](agents/coordinator/system.md) | ultimate | Bash, Read, Write | None |
| executor | [agents/executor/system.md](agents/executor/system.md) | ultimate | Read | sim_trade_input_order, sim_trade_cancel_order, sim_trade_modify_order, sim_trade_account_list, sim_trade_cash_info, sim_trade_position_list, sim_trade_history_order_list, sim_trade_max_buy_sell |
| manager | [agents/manager/system.md](agents/manager/system.md) | ultimate | None | None |
| quick | [agents/quick/system.md](agents/quick/system.md) | efficient | None | None |

## 3. Permission policy

Each `agents/<name>/agent.json` uses `agents/permissions.json` via identical
`mcp_toolset.configs` entries. All real-money and crypto order tools are disabled
and always_deny. Simulated input/cancel/modify order tools default to always_ask
for executor and are denied for everyone else. A logged autonomy decision may
enable the deploy builder's explicit allow override. All other named tools are denied unless
explicitly allowed in the registry. Additional discovered MCP tools are disabled
by the deploy builder; full inventory and effective policy must be verified.
No empty built-in enabled_tools array is permitted because Qoder enables all
built-ins in that case. Shell access is not a broker safety sandbox.

## 4. MCP and account connections

Every agent declares the Moomoo connection as `name=moomoo`, `type=url`, with
`${MOOMOO_MCP_URL}` resolved to the verified official endpoint at deployment.
Authentication uses the existing vault whose display_name is `moomoo-mcp`.
Cloud Sessions bind vault_ids; Forward Templates bind the vaults map. No secrets
are stored here. Executor verifies configured acc_id, account_type=2, challenge
title and US market before forwarding exact code-approved ticket args.

## 5. Skill bindings and versions

Every agent has `skills: []`: no Qoder skills are currently bound and no skill
versions are invented. Future bindings must use `{type, skill_id, version}` with
an actual immutable version string, recorded here. Child Agent references pin
version 1 for initial creation; live IDs/versions remain pending until deployment.

## 6. Session ownership

Coordinator delegates to analyst, bull, bear, manager, quick and executor.
Auditor is a separate new Session, never a child in that shared Session.
Coordinator is the sole file writer within morning/watch Sessions and owns
clock checks (date -u), phase commands and persistence. Executor returns exact
broker replies; analyst returns research or requested quotes; classifiers return
JSON. Children never write files, execute scripts or verify time. Auditor owns
its separate Session's files. Only the current locked event writer appends JSONL.
Durable persistence, account-wide locking, calendar enforcement and code ticket
idempotency are required before live paper trading. Top-five quick opinions are
logged with secondOpinion=true and excluded from risk inputs.

Coordinator also owns watch sessions; no separate watcher agent exists. Follow
its numbered Session procedures and the auditor's independent audit procedure.
They use scripts/run_session.py; halt if any required command is absent.
Run session_info and gather_inputs after baseline reconciliation for both kinds.
Morning saves verbatim child replies then runs ingest_ratings; quotes come LAST
through analyst and convert_quotes. After prepare, require dispatch_check ok:true
for EACH ticket before handing exact args to executor for one order. AUTONOMY-01
and deployed always_allow authorize that paper order without another approval
request; never bypass effective policy. Follow docs/runtime.md for exact commands.
Renew with under 10 minutes remaining and work left, capped at 120 minutes total. Morning/watch phases are start,
preflight, reconcile, plan, prepare, record, reconcile, finish; audit phases are
start, reconcile, grade_calls, score_hypotheses, finish. Screening starts only
after the morning baseline. Watch requires preflight and never classifies.
Stop on skipped=true, a nonzero exit or lease expiry. Finish saves/unlocks;
abort saves failures when ownership permits. Never repeat cleanup after a skip
or reported automatic abort success. Preserve/report unsaved evidence on failure.
The morning cron is 09:35 New York (22:35 SGT); if start skips, stop; do not wait under its lease.
Quick reason is at most 3 sentences and at most 400 characters; schema stays 600.

## 7. Deployment and reporting

Use `scripts/qca_deploy.py` for a credential-free dry run. Do not apply or publish
without authorization. See [docs/agents.md](docs/agents.md) for exact field
mappings, model sources, integrations, staged Slack pairing and open questions.
Auditor reports verified fills, drawdown, decisions, uncertainty and three prompts:
what surprised me; what I would change; what the agents got right or wrong.
Final output is delivered by its paired Slack schedule sink, not a direct token.

## 8. Evaluation and provenance records

Run `.venv/Scripts/python -m pytest` for offline contract tests. Collect real Qoder
outputs for the four fixed evals and run `scripts/run_evals.py --outputs <folder>`.
The evaluator calls no model and diffs against the previous report. Do not label
synthetic test outputs as model evaluations. Freeze with scripts/hash_prompts.py.
After a cloud fetch or change, append a timestamped record with actual Agent ID,
cloud version, local revision and change summary. Do not fill pending with guesses.

### analyst

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***q45l (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local analyst prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### auditor

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***8zys (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local auditor prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### bear

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***78l4 (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local bear prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### bull

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***ugkv (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local bull prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### coordinator

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***fbza (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Changed at (UTC): 2026-11-17T06:55:00Z Agent ID: pending Cloud version: pending Local revision: build/12-prefreeze Change summary: Added debate-output ingestion instructions; local only, cloud not queried or changed. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local coordinator prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### executor

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***xlsm (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local executor prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### manager

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***dflq (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Changed at (UTC): 2026-11-17T06:55:00Z Agent ID: pending Cloud version: pending Local revision: build/12-prefreeze Change summary: Required raw JSON and a maximum 600-character reason; local only, cloud not queried or changed. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local manager prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### quick

<!-- Verified at (UTC): 2026-11-17T07:16:00Z Agent ID: ***3gsf (masked) Cloud version: 2 Local revision: fbac2f96c3f6901acd9f4a2f69563256ed6fdf9f Change summary: Updated existing resource and verified prompt, model and permissions by GET; executor approval remains ask. -->

<!-- Changed at (UTC): 2026-11-17T06:55:00Z Agent ID: pending Cloud version: pending Local revision: build/12-prefreeze Change summary: Required raw JSON and a maximum 600-character reason; local only, cloud not queried or changed. -->

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local quick prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->


## Debate output contract (build/13b-debate-format)

Bull and bear return raw JSON only, without Markdown fences, with exactly
`decisionId`, `stance`, `argument`, and `itemIds`. No extra provenance fields:
`ticker`, `newsCutoff`, `model`, and `promptVersion` remain input context.
`argument` is at most 150 words. Citations must identify supplied brief items
published at or before the trusted cutoff; exactly-at-cutoff items are eligible.
Neither arguments nor manager reasoning may rely on later items, including later
items present in the brief or another agent's output. Use empty citations when
nothing qualifies. The strict collector is unchanged; regression tests cover
both roles, extra keys, later citations, and valid boundary/empty citations.
Embedded agent JSON prompts mirror the authoritative system.md files.

Recompute `scripts/hash_prompts.py` after prompt changes. Redeploy only the
pushed main SHA and verify existing resources by GET before read-only evals.
Cloud results for this revision are recorded separately after actual execution;
this contract change alone does not establish an eval pass or authorize orders.
