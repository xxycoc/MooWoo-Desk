"""Check one already-prepared order immediately before its broker tool call."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import re

import _common
from _execution import frozen_config, read_json
from hash_prompts import prompt_version
from moowoo.execution import decision_events, execution_ready, load_tickets, safe_reason, note
from moowoo import calendar, config
from moowoo.core import require_core_fills
from moowoo.portfolio import PortfolioState
from moowoo.desk_data import limit_price
from convert_quotes import quote_rows, parse_quote
from moowoo.persistence import LedgerError, LedgerStore
from moowoo.runlock import require_owned
from moowoo.runtime_logs import existing_log, index_logs
from moowoo.tickets import to_sim_order
from persist_ledger import redact_error
from run_session import validate_dispatch


class StaleQuote(ValueError):
    pass


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
    if type(attempt) is not int or not 1 <= attempt <= 2:
        raise ValueError("prepared attempt must be integer 1 or 2")
    withheld = [event for event in events if event.get("executionAction") == "dispatch_withheld"]
    last_withheld = withheld[-1]["seq"] if withheld else -1
    if any(event["type"] == "order_submitted" or event.get("executionAction") == "skip"
           or (event.get("executionAction") == "dispatch_authorized" and event["attempt"] == attempt
               and event["seq"] > last_withheld)
           or (event.get("executionAction") == "placement_failed" and event["attempt"] == attempt)
           for event in events):
        raise ValueError("prepared attempt is already resolved or skipped")
    quote_attempt = 1 + sum(event.get("executionAction") == "quote_refresh"
                            for event in events)
    orders = []
    for path in (root / "receipts" / run_id).glob("prepare-*.json"):
        orders.extend(order for order in read_json(path).get("orders", [])
                      if order["decisionId"] == args.decision_id and order["attempt"] == attempt)
    if len(orders) != 1 or orders[0]["tool"] != "sim_trade_input_order" or orders[0]["args"] != to_sim_order(ticket):
        raise ValueError("missing, ambiguous or mismatched prepared tool arguments")
    # Persist intent before handoff: a crash afterwards is uncertain, never safe to retry.
    quote_path = root / "inputs" / run_id / f"quotes-raw-{ticket.ticker}.json"
    deadline = None

    def check_quote():
        nonlocal deadline
        rows = quote_rows(read_json(quote_path))
        if len(rows) != 1:
            raise ValueError("dispatch requires exactly one quote")
        symbol, quote = parse_quote(rows[0])
        stamp = calendar.local_time(quote["ts"])
        deadline = calendar.utc_stamp(stamp + timedelta(seconds=config.STALE_PRICE_SECONDS))
        current = now or datetime.now(timezone.utc)
        validate_dispatch(dict(tickets=selected), current)
        if symbol != ticket.ticker:
            raise ValueError("fresh quote symbol mismatch")
        age = (calendar.local_time(current) - stamp).total_seconds()
        if age < 0:
            raise ValueError("future quote timestamp")
        if (ticket.side == "BUY" and (quote["ask"] - quote["bid"]) /
                ((quote["ask"] + quote["bid"]) / 2) > config.MAX_SPREAD + 1e-12):
            raise ValueError("fresh quote spread exceeds frozen limit")
        # The prepared limit stays fixed; it only has to remain marketable against the fresh quote,
        # so a buy never pays above, and a sell never accepts below, the planned price (addendum 21).
        fresh = limit_price(quote, ticket.side)
        if (fresh > ticket.limitPrice) if ticket.side == "BUY" else (fresh < ticket.limitPrice):
            raise ValueError("fresh quote moved past the ticket limit price")
        if ticket.sleeve == "core" and ticket.side == "BUY":
            state = PortfolioState.from_dict(read_json(root / "state.json"))
            prices = {name: p["marketPrice"] for name, p in state.positions.items()}
            prices[ticket.ticker] = quote["last"]
            require_core_fills(ticket, manifest, state, log, prices)
        if age > config.STALE_PRICE_SECONDS:
            raise StaleQuote("stale quote timestamp")

    def skip_quote(exc, *, before_authorization=False):
        if isinstance(exc, StaleQuote) and quote_attempt < 2:
            if not before_authorization:
                # No ok:true was returned, so this authorization never reached the caller.
                note(log, ticket, "dispatch_withheld", attempt=attempt, reason="quote expired during checkpoint")
            note(log, ticket, "quote_refresh", attempt=attempt, quoteAttempt=quote_attempt,
                 reason="stale quote; fetch one fresh quote before rechecking")
            store.save("Checkpoint quote refresh", context["holder"], release=False)
            return dict(ok=False, skipped=False, retryable=True, quoteAttempt=quote_attempt,
                        attempt=attempt, decisionId=ticket.decisionId, reason="stale quote timestamp")
        reason = safe_reason(str(exc)) if isinstance(exc, ValueError) else "invalid or missing fresh quote"
        note(log, ticket, "skip", attempt=attempt, reason=reason, quoteDeadline=deadline)
        store.save("Skip ticket at dispatch", context["holder"], release=False)
        return dict(ok=False, skipped=True, decisionId=ticket.decisionId, reason=reason, quoteDeadline=deadline)

    require_owned(store, context["holder"], now)
    validate_dispatch(dict(tickets=selected), now or datetime.now(timezone.utc))
    try:
        check_quote()
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        return skip_quote(exc, before_authorization=True)
    note(log, ticket, "dispatch_authorized", attempt=attempt, ticketHash=ticket.ticketHash,
         quoteDeadline=deadline, quoteFile=quote_path.relative_to(root).as_posix())
    store.save("Checkpoint dispatch before broker handoff", context["holder"], release=False)
    require_owned(store, context["holder"], now)
    validate_dispatch(dict(tickets=selected), now or datetime.now(timezone.utc))
    try:
        check_quote()
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        return skip_quote(exc)
    return dict(ok=True, decisionId=args.decision_id, tool=orders[0]["tool"],
                attempt=attempt, args=orders[0]["args"], quoteDeadline=deadline)



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
