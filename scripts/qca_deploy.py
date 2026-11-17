"""Build Qoder API payloads offline; --apply explicitly creates cloud resources.

No sessions are launched by this script. Applying schedules can start future runs.
Dry run never reads .env, contacts Qoder, or loads credentials.
"""

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from hash_prompts import prompt_version

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.qoder.com/api/v1"
ROLES = ("analyst", "bull", "bear", "manager", "quick", "executor", "auditor", "coordinator")
SETTING_KEYS = {"MOOMOO_MCP_URL", "MOOMOO_ACCOUNT_ID", "MOOMOO_MARKET", "MOOMOO_CHALLENGE_TITLE",
                "REPO_REVISION", "IDENTITY_ID", "SLACK_CHANNEL_PAIRING_ID", "moomoo_tool_names"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve(value, bindings):
    """Resolve explicit local manifest references, including vault-map keys."""
    if isinstance(value, dict):
        return {resolve(k, bindings): resolve(v, bindings) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, bindings) for v in value]
    if isinstance(value, str):
        for key, replacement in bindings.items():
            token = "${" + key + "}"
            if value == token:
                return replacement
            if token in value:
                value = value.replace(token, str(replacement))
    return value


def check_settings(settings, *, complete=False, stage="schedules"):
    unknown = set(settings) - SETTING_KEYS
    if unknown:
        raise ValueError("unknown deployment setting; credentials do not belong in settings")
    for key, value in settings.items():
        if key == "moomoo_tool_names":
            if not isinstance(value, list) or not value or any(
                not isinstance(t, str) or not re.fullmatch(r"[A-Za-z0-9_]+", t) for t in value
            ):
                raise ValueError("moomoo_tool_names must be the verified MCP tool inventory")
        elif not isinstance(value, str) or not value.strip() or "${" in value:
            raise ValueError(f"invalid setting: {key}")
    url = settings.get("MOOMOO_MCP_URL")
    if url:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("MCP endpoint must be HTTPS without credentials, query or fragment")
    revision = settings.get("REPO_REVISION")
    if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("REPO_REVISION must be a pinned 40-character commit SHA")
    if settings.get("MOOMOO_MARKET", "100") != "100":
        raise ValueError("only US market is permitted")
    required = SETTING_KEYS - ({"SLACK_CHANNEL_PAIRING_ID"} if stage == "resources" else set())
    if complete and required - settings.keys():
        raise ValueError("apply requires all nonsecret settings, including verified MCP inventory")


def build_payloads(settings=None, root=ROOT, *, executor_approval="ask"):
    if executor_approval not in ("ask", "allow"):
        raise ValueError("executor approval must be ask or allow")
    settings = settings or {}
    check_settings(settings)
    root = Path(root)
    policy = read_json(root / "agents/permissions.json")
    version = prompt_version(root)
    operations = []

    def add(key, endpoint, body):
        operations.append({"key": key, "method": "POST", "path": endpoint, "body": body})

    setup = "\n".join([
        "set -euo pipefail",
        "mkdir -p /data/workspace",
        "git clone https://github.com/xxycoc/MooWoo-Desk /data/workspace/MooWoo-Desk",
        "cd /data/workspace/MooWoo-Desk",
        "git checkout --detach ${REPO_REVISION}",
        "python3 -m pip install -e '.[dev]'",
        "python3 -m pytest -q || { echo 'Cloud setup failed: pytest failed' >&2; exit 1; }",
        "test -f scripts/plan_session.py",
        f'test "$(python3 scripts/hash_prompts.py)" = "promptVersion={version}"',
    ])
    startup = "\n".join([
        "set -euo pipefail",
        "python3 - <<'PY'",
        "import json, os",
        "from pathlib import Path",
        "keys = ('MOOMOO_ACCOUNT_ID', 'MOOMOO_MARKET', 'MOOMOO_CHALLENGE_TITLE')",
        "values = {k: os.environ[k] for k in keys}",
        "assert all(v.strip() and '${' not in v for v in values.values())",
        "assert values['MOOMOO_MARKET'] == '100'",
        "Path('/data/workspace/account-context.json').write_text(json.dumps(values))",
        "PY",
    ])
    add("environment", "/cloud/environments", {
        "name": "moowoo-desk-agents-v1", "description": "Paper trading; persistence must be configured before trading",
        "config": {"type": "cloud", "packages": {"apt": ["git"],
                    "pip": ["numpy>=2.5,<3", "pandas>=3.0,<4", "yfinance>=1.8"]},
                   "setup_script": setup, "startup_script": startup},
        "metadata": {"promptVersion": version},
    })
    agents = {}
    for role in ROLES:
        agent = read_json(root / f"agents/{role}/agent.json")
        agent["system"] = (root / f"agents/{role}/system.md").read_text(encoding="utf-8")
        agent["metadata"]["promptVersion"] = version
        configs = deepcopy(policy["agents"][role]["configs"])
        if role == "executor":
            for tool in configs:
                if tool["name"] in policy["simulated_order_tools"]:
                    tool["permission_policy"]["type"] = "always_ask" if executor_approval == "ask" else "always_allow"
            agent["metadata"]["executorApproval"] = executor_approval
        known = {c["name"] for c in configs}
        # Qoder documents per-tool configs, not an MCP wildcard deny policy.
        for name in sorted(set(settings.get("moomoo_tool_names", [])) - known):
            configs.append({"name": name, "enabled": False,
                            "permission_policy": {"type": "always_deny"}})
        for toolset in agent["tools"]:
            if toolset["type"] == "mcp_toolset":
                toolset["configs"] = configs
        agents[role] = agent
        add("agent." + role, "/cloud/agents", agent)

    environment_variables = {k: "${" + k + "}" for k in
                             ("MOOMOO_ACCOUNT_ID", "MOOMOO_MARKET", "MOOMOO_CHALLENGE_TITLE")}
    for role in ("coordinator", "auditor"):
        template = {k: deepcopy(v) for k, v in agents[role].items()
                    if k in {"name", "description", "model", "system", "tools", "skills", "mcp_servers", "multiagent", "metadata"}}
        template.update(name=f"moowoo-{role}-v1", environment_id="${environment.id}",
                        vaults={"${vault.moomoo-mcp.id}": {"enabled": True}},
                        environment_variables=environment_variables)
        add("template." + role, "/forward/templates", template)

    def schedule(key, role, expression, timezone, message, *, slack=False):
        add("schedule." + key, "/forward/schedules", {
            "identity_id": "${IDENTITY_ID}", "template_id": "${template." + role + ".id}",
            "name": "moowoo-" + key, "environment_id": "${environment.id}",
            "initial_events": [{"type": "user.message", "content": message}],
            "trigger_policy": {"type": "cron", "expression": expression, "timezone": timezone},
            "execution": {"session_mode": "new_session", "max_concurrent_runs": 1,
                          "max_attempts": 1, "timeout_ms": 1800000},
            "sinks": [{"type": "im_channel", "channel_pairing_id": "${SLACK_CHANNEL_PAIRING_ID}"}] if slack else [],
            "metadata": {"window_start": "2026-11-17", "window_end": "2026-11-27",
                         "requires_exchange_calendar_guard": True},
        })

    guard = ("Require verified exchange calendar, durable single-writer state and committed prompt hash. "
             "Do nothing outside 17-27 Nov 2026 or on non-trading days. ")
    schedule("morning", "coordinator", "30 21 * * 1-5", "Asia/Singapore", guard + "Run the morning session.")
    # Three cron expressions represent exactly 09:30, 10:00..15:30, 16:00 NY.
    for suffix, cron in (("open", "30 9 * * 1-5"), ("regular", "0,30 10-15 * * 1-5"), ("close", "0 16 * * 1-5")):
        schedule("watcher-" + suffix, "coordinator", cron, "America/New_York",
                 guard + "Watcher mode: reconcile and run the installed code risk watcher. "
                 "No entries in first five minutes, no new entries on Nov 27. "
                 "No action after an early close. Halt if deterministic watcher is missing.")
    schedule("audit", "auditor", "10 16 * * 1-5", "America/New_York",
             guard + "Consume the persisted audit handoff in this separate Session; reconcile, report and ask reflections.", slack=True)

    return resolve({
        "promptVersion": version,
        "executorApproval": executor_approval,
        "approvalDecisionRequired": executor_approval == "allow",
        "vault_lookup": {"method": "GET", "path": "/cloud/vaults?name=moomoo-mcp&limit=100",
                         "display_name": "moomoo-mcp"},
        "operations": operations,
        "session_example": {"agent": {"type": "agent", "id": "${agent.auditor.id}", "version": 1},
                            "environment_id": "${environment.id}", "vault_ids": ["${vault.moomoo-mcp.id}"],
                            "environment_variables": environment_variables},
        "unresolved_runtime_requirements": [
            "Publish pinned revision only after authorized merge; setup fails without risk desk integration",
            "Commit preregistration prompt addendum before first order",
            "Persist and restore event logs, checkpoints, ticket receipts and audit handoff",
            "Provide cross-schedule locking and code watcher/session-calendar enforcement",
            "Verify Moomoo account response fields, official endpoint and full tool inventory",
            "Pair auditor Template and Identity to Slack; use that pairing ID for its sink",
            "Verify effective Forward Identity config does not override permissions or models",
        ],
    }, settings)


def load_pat(path):
    """Only --apply reads this file. Never expand shell expressions or echo it."""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "QODER_PAT":
            value = value.strip().strip("\"'")
            if value:
                return value
    raise ValueError("QODER_PAT is missing from .env")


def api_request(method, path, token, body=None):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    if data is not None and path.startswith("/forward/"):
        headers["Idempotency-Key"] = hashlib.sha256(path.encode() + data).hexdigest()
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not print response bodies or request objects containing authentication.
        raise RuntimeError(f"Qoder {method} {path.split('?')[0]} failed: HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("Qoder transport failed; inspect remote state before retrying") from None


def load_receipts(path):
    receipts = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    bindings = {}
    for receipt in receipts:
        key = receipt["key"] + ".id"
        if key in bindings:
            raise ValueError("duplicate deployment receipt; inspect remote state")
        bindings[key] = receipt["id"]
    return {"bindings": bindings, "receipts": receipts}


def apply_payloads(manifest, settings, token, request=api_request, *, stage="resources", prior=None,
                   receipt_path=None):
    if stage not in ("resources", "schedules"):
        raise ValueError("stage must be resources or schedules")
    check_settings(settings, complete=True, stage=stage)
    models = {m["id"]: m for m in request("GET", "/cloud/models", token)["data"]}
    for name in ("ultimate", "efficient"):
        if name not in models or not models[name].get("is_enabled"):
            raise ValueError(f"configured model is unavailable: {name}")
    costs = [models[m].get("price_factor") for m in ("efficient", "ultimate")]
    if any(type(c) not in (int, float) for c in costs) or not costs[0] < costs[1]:
        raise ValueError("catalog does not establish efficient is cheaper than ultimate")
    inventory = set(settings["moomoo_tool_names"])
    policy = read_json(ROOT / "agents/permissions.json")
    allowed = {c["name"] for p in policy["agents"].values() for c in p["configs"] if c["enabled"]}
    if not allowed <= inventory:
        raise ValueError("Moomoo inventory is missing required tools")
    vaults = []
    path = manifest["vault_lookup"]["path"]
    while True:
        page = request("GET", path, token)
        vaults.extend(v for v in page["data"] if v["display_name"] == "moomoo-mcp" and not v.get("archived_at"))
        if not page.get("has_more"):
            break
        cursor = page.get("next_page")
        if not cursor:
            raise ValueError("vault pagination missing cursor")
        path = manifest["vault_lookup"]["path"] + "&page=" + urllib.parse.quote(cursor, safe="")
    if len(vaults) != 1:
        raise ValueError("expected exactly one active vault named moomoo-mcp")
    bindings = dict((prior or {}).get("bindings", {}))
    bindings["vault.moomoo-mcp.id"] = vaults[0]["id"]
    if stage == "schedules" and not {"environment.id", "template.coordinator.id", "template.auditor.id"} <= bindings.keys():
        raise ValueError("schedule stage requires the resource receipt file")
    receipts = list((prior or {}).get("receipts", []))
    for op in manifest["operations"]:
        is_schedule = op["key"].startswith("schedule.")
        if is_schedule != (stage == "schedules"):
            continue
        if op["key"] + ".id" in bindings:
            raise ValueError(f"resource already recorded: {op['key']}; inspect remote state before updating")
        body = resolve(op["body"], bindings)
        if re.search(r"\$\{[A-Za-z0-9_.-]+\}", json.dumps(body)):
            raise ValueError(f"unresolved reference in {op['key']}")
        result = request(op["method"], op["path"], token, body)
        bindings[op["key"] + ".id"] = result["id"]
        receipt = {"key": op["key"], "id": result["id"], "version": result.get("version")}
        receipts.append(receipt)
        if receipt_path is not None:
            destination = Path(receipt_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Append receipts instead of repeatedly replacing a file Windows may scan.
            with destination.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(receipt) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        print(json.dumps(receipt), flush=True)
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, help="nonsecret JSON deployment bindings")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--executor-approval", choices=("ask", "allow"), default="ask")
    parser.add_argument("--approval-log", type=Path, help="verified rule_change log required to apply allow")
    parser.add_argument("--stage", choices=("resources", "schedules"), default="resources")
    parser.add_argument("--receipts", type=Path, default=ROOT / ".cache/qca-deployment.jsonl")
    args = parser.parse_args()
    settings = read_json(args.settings) if args.settings else {}
    manifest = build_payloads(settings, executor_approval=args.executor_approval)
    if args.apply:
        if args.executor_approval == "allow":
            import _common
            from moowoo.ledger import EventLog
            if not args.approval_log:
                parser.error("allow requires --approval-log with executor_approval rule_change")
            decisions = [event for event in EventLog(args.approval_log).read()
                         if event["type"] == "rule_change" and event["ruleId"] == "executor_approval"
                         and not event["drill"]]
            if not decisions or decisions[-1]["after"] != "allow":
                parser.error("latest executor_approval decision must authorize allow")
        check_settings(settings, complete=True, stage=args.stage)
        prior = load_receipts(args.receipts) if args.receipts.exists() else None
        apply_payloads(manifest, settings, load_pat(ROOT / ".env"), stage=args.stage,
                       prior=prior, receipt_path=args.receipts)
    else:
        print(json.dumps(manifest, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
