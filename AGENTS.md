# MooWoo Desk agent handbook

## 1. Binding rules

PREREGISTRATION.md is binding. Paper trading only, US stocks and ETFs, long only.
No first live order until the owner commits the dated promptVersion addendum.
LLMs do not size positions or place discretionary orders. Code issues tickets.
Never edit frozen configuration or bypass permissions. Missing inputs halt.

## 2. Agent registry

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
and always_deny. Simulated input/cancel/modify order tools are always_allow only
for executor and denied for everyone else. All other named tools are denied unless
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
Only the current locked event writer appends JSONL. Workers return transcripts.
Durable persistence, account-wide locking, calendar enforcement and code ticket
idempotency are required before live paper trading. Top-five quick opinions are
logged with secondOpinion=true and excluded from risk inputs.

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

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local analyst prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### auditor

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local auditor prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### bear

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local bear prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### bull

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local bull prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### coordinator

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local coordinator prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### executor

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local executor prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### manager

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local manager prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->

### quick

<!-- Retrieved at (UTC): 2026-11-17T04:27:36Z Agent ID: pending  Cloud version: pending  Local revision: agents-v1  Change summary: Created local quick prompt and policy from retrieved Qoder docs; no cloud Agent fetched. -->
