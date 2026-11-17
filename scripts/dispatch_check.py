"""Check one already-prepared order immediately before its broker tool call."""

import argparse
from datetime import datetime, timezone
import json
import re

import _common
from _execution import frozen_config, read_json
from hash_prompts import prompt_version
from moowoo.execution import decision_events, execution_ready, load_tickets, safe_reason
from moowoo.persistence import LedgerError, LedgerStore
from moowoo.runlock import require_owned
from moowoo.runtime_logs import existing_log, index_logs
from moowoo.tickets import to_sim_order
from persist_ledger import redact_error
from run_session import validate_dispatch


def run(args, now=None):
    store = LedgerStore(args.dir)
    root = store.directory
    context = read_json(root / ".session.json")
    if context["kind"] != args.kind or context["phase"] not in ("prepare", "record"):
        raise ValueError("dispatch requires the matching prepared session")
    run_id = context["runId"]
    if not isinstance(run_id, str) or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
        raise ValueError("invalid session identity")
    require_owned(store, context["holder"], now)
    manifest = read_json(root / "tickets" / f"{run_id}.json")
    selected = [ticket for ticket in manifest["tickets"] if ticket["decisionId"] == args.decision_id]
    if len(selected) != 1:
        raise ValueError("decision missing or duplicated in ticket manifest")
    logs = index_logs(existing_log(path) for path in (root / "logs").glob("*.jsonl"))
    log = logs[run_id]
    frozen = frozen_config()
    ticket = load_tickets(manifest | dict(tickets=selected), log, frozen["configHash"])[args.decision_id]
    execution_ready(log.read(), frozen["configHash"], prompt_version())
    events = decision_events(log, args.decision_id)
    attempts = [event for event in events if event.get("executionAction") == "prepared"]
    if not attempts or attempts[-1]["ticketHash"] != ticket.ticketHash:
        raise ValueError("ticket has no matching prepared attempt")
    attempt = attempts[-1]["attempt"]
    if any(event["type"] == "order_submitted" or event.get("executionAction") == "skip"
           or (event.get("executionAction") == "placement_failed" and event["attempt"] == attempt)
           for event in events):
        raise ValueError("prepared attempt is already resolved or skipped")
    orders = []
    for path in (root / "receipts" / run_id).glob("prepare-*.json"):
        orders.extend(order for order in read_json(path).get("orders", [])
                      if order["decisionId"] == args.decision_id and order["attempt"] == attempt)
    if len(orders) != 1 or orders[0]["tool"] != "sim_trade_input_order" or orders[0]["args"] != to_sim_order(ticket):
        raise ValueError("missing, ambiguous or mismatched prepared tool arguments")
    require_owned(store, context["holder"], now)
    validate_dispatch(dict(tickets=selected), now or datetime.now(timezone.utc))
    return dict(ok=True, decisionId=args.decision_id, args=orders[0]["args"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("morning", "watch"))
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--dir", default="runtime")
    args = parser.parse_args()
    try:
        result = run(args)
    except (ValueError, KeyError, TypeError, OSError, LedgerError) as exc:
        reason = "invalid or missing runtime data" if isinstance(exc, (KeyError, TypeError, OSError)) else str(exc)
        reason = re.sub(r"\d{7,}", "[REDACTED]", redact_error(safe_reason(reason)))
        print(json.dumps(dict(ok=False, reason=reason)))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
