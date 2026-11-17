"""One offline watcher tick; the scheduler invokes it every thirty minutes."""

import argparse
from pathlib import Path

from _execution import atomic_json, command, frozen_config, read_json
from plan_session import ROOT, load_bars
from moowoo import config as C
from moowoo import calendar
from moowoo.desk_data import instant
from moowoo.execution import require_not_halted
from moowoo.exits import propose_exits
from moowoo.portfolio import PortfolioState
from moowoo.risk import check
from moowoo.tickets import OrderTicket


def run(args, log):
    snapshot = read_json(args.quotes)
    now = calendar.local_time(snapshot["now"])
    skipped = calendar.skip(log, now, "watch") or calendar.skip_first_minutes(log, now, C.NO_ORDERS_FIRST_MINUTES)
    if skipped:
        return skipped
    frozen = frozen_config()
    state = PortfolioState.from_dict(read_json(args.state))
    if state.halted and state.tier != "kill":
        raise ValueError("state halted; reconcile or explicitly restart before watching")
    require_not_halted(log.read())
    snapshot["now"] = calendar.utc_stamp(now)
    session = snapshot["sessionDate"]
    opened, closed = calendar.session_open(now), calendar.session_close(now)
    if now.date().isoformat() != session:
        raise ValueError("invalid regular-session date")
    if args.bars_asof > session or (args.bars_asof == session and now < closed):
        raise ValueError("bars-asof includes incomplete session")
    bars, errors = load_bars(args.bars, args.bars_asof)
    quotes = snapshot["quotes"]
    for name, position in state.positions.items():
        if position["kind"] == "core" and state.tier != "kill":
            continue
        if name not in quotes or not 0 <= (now-instant(quotes[name]["ts"])).total_seconds() <= C.STALE_PRICE_SECONDS:
            raise ValueError(f"missing or stale watcher quote: {name}")
        if position["kind"] != "core" and name in errors:
            raise ValueError(errors[name])
    outcome = propose_exits(state, bars, quotes, session, log.runId)
    if outcome["skipped"]:
        raise ValueError(str(outcome["skipped"]))
    for name, changes in outcome["updates"].items():
        if changes["stop"] < state.positions[name].get("stop", 0):
            raise ValueError("watcher attempted to loosen stop")
        state.positions[name].update(changes)
    durable = {event["decisionId"]: event["approvedTicket"] for event in log.read()
               if event["type"] == "risk_verdict" and "approvedTicket" in event and not event["drill"]}
    if any(payload["side"] != "SELL" for payload in durable.values()):
        raise ValueError("watcher requires a separate exit run/log; entry manifest must remain immutable")
    for decision_id, payload in durable.items():
        if decision_id not in state.ticketedDecisionIds:
            state.reserve(OrderTicket(**payload))
    created = []
    for proposal in outcome["proposals"]:
        if proposal["decisionId"] in durable:
            continue
        verdict = check(proposal, state, {})
        if verdict["verdict"] == "veto":
            raise ValueError("watch exit ID already used; a new watcher run/log is required")
        ticket = OrderTicket.from_proposal(proposal, verdict, frozen["configHash"], snapshot["now"])
        log.append("risk_verdict", verdict | dict(approvedTicket=ticket.to_dict()))
        durable[ticket.decisionId] = ticket.to_dict()
        state.reserve(ticket)
        created.append(ticket.decisionId)
    for payload in durable.values():
        if "stop" in payload["reason"] and not any(event["type"] == "stop_hit" and
                event["decisionId"] == payload["decisionId"] for event in log.read()):
            position = state.positions[payload["ticker"]]
            log.append("stop_hit", dict(ticker=payload["ticker"], entry=position["entryPrice"],
                stop=payload["stop"], exitOrderId="", exitDecisionId=payload["decisionId"], pendingApproval=True))
    destination = Path(args.tickets_dir) / f"{log.runId}.json"
    atomic_json(destination, dict(runId=log.runId, configHash=frozen["configHash"],
                tickets=list(durable.values()), executionAuthorized=False))
    atomic_json(args.state, state.to_dict())
    return dict(tickets=str(destination), created=created, stopUpdates=outcome["updates"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "quotes", "bars-asof", "log"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--bars", default=str(ROOT / ".cache/desk/bars.json"))
    parser.add_argument("--tickets-dir", default=str(ROOT / "tickets"))
    return command(parser.parse_args(), run, persist_halt=True)


if __name__ == "__main__":
    raise SystemExit(main())
