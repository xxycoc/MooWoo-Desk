"""Plan offline tickets from a snapshot, ratings, cached daily bars and timestamped quotes."""

import argparse
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile

import _common  # noqa: F401
import pandas as pd

from moowoo import config as C
from moowoo import calendar
from moowoo.rules import AUTONOMY_CHANGE, PICKS_CHANGE, SIZING_CHANGE, TOPOLOGY_CHANGE, CORE_REBALANCE_CHANGE, REGIME_SIZING_CHANGE, CORE_CASH_CHANGE
from moowoo.core import propose_core, projected_core_state
from moowoo.desk_data import daily_frame, instant
from moowoo.events import canonical_bytes
from moowoo.exits import propose_exits
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.risk import check
from moowoo.sizing import propose_entry
from moowoo.stepup import evaluate
from moowoo.tickets import OrderTicket
from moowoo.tiers import update

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
        temporary = stream.name
        stream.write(canonical_bytes(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def frozen_config():
    frozen = read_json(ROOT / "config/frozen-2026-11-17.json")
    calculated = hashlib.sha256(canonical_bytes({key: value for key, value in frozen.items()
                                                if key != "configHash"})).hexdigest()
    actual = {key: value for key, value in vars(C).items() if not key.startswith("_")}
    additions = [json.loads(line) for line in (ROOT / "config/rule-ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    expected_addendum = dict(date="2026-11-17", ruleId="FEES-01", before=None,
        after=dict(FEE_PER_ORDER=.99, FEE_PER_SHARE_SOLD=.000166, FEE_SELL_CAP=8.30, MIN_ENTRY_NOTIONAL=2000),
        reason="competition rules section 8 fees; addendum before first trade", effectiveFrom="first session")
    if additions != [expected_addendum, AUTONOMY_CHANGE, PICKS_CHANGE, TOPOLOGY_CHANGE, SIZING_CHANGE, CORE_REBALANCE_CHANGE, REGIME_SIZING_CHANGE, CORE_CASH_CHANGE]:
        raise ValueError("unrecognized rule addendum")
    expected = (frozen["config"] | expected_addendum["after"] | PICKS_CHANGE["after"]
                | SIZING_CHANGE["after"] | CORE_REBALANCE_CHANGE["after"]
                | REGIME_SIZING_CHANGE["after"] | CORE_CASH_CHANGE["after"])
    if calculated != frozen["configHash"] or canonical_bytes(actual) != canonical_bytes(expected):
        raise ValueError("frozen configuration mismatch; planning refused")
    return frozen


def load_bars(path, asof):
    source = Path(path)
    if source.is_dir():
        payload = {file.stem: read_json(file) for file in sorted(source.glob("*.json"))}
    else:
        payload = read_json(source)
    bars, errors = {}, {}
    for ticker, values in payload.items():
        try:
            if isinstance(values, dict) and "bars" in values:
                values = pd.read_json(StringIO(values["bars"]), orient="table")
            frame = daily_frame(values)
            frame = frame.loc[frame.index <= asof]
            if frame.empty or str(frame.index[-1].date()) != asof:
                raise ValueError("no completed bar on bars-asof")
            bars[ticker] = frame
        except (ValueError, KeyError, TypeError) as exc:
            errors[ticker] = str(exc)
    return bars, errors


def plan(args):
    snapshot = read_json(args.quotes)
    run_id = args.run_id or snapshot.get("runId", f"{snapshot['sessionDate']}-us")
    log = EventLog(args.log, runId=run_id)
    with log.locked():
        return _plan(args, log)


def _plan(args, log):
    snapshot = read_json(args.quotes)
    now = calendar.local_time(snapshot["now"])
    skipped = calendar.skip(log, now, "morning") or calendar.skip_first_minutes(log, now, C.NO_ORDERS_FIRST_MINUTES)
    if skipped:
        return skipped
    frozen = frozen_config()
    state = PortfolioState.from_dict(read_json(args.state))
    snapshot["now"] = calendar.utc_stamp(now)
    opened, closed = calendar.session_open(now), calendar.session_close(now)
    session = snapshot["sessionDate"]
    if now.date().isoformat() != session:
        raise ValueError("invalid regular-session schedule")
    pd.Timestamp(args.bars_asof)
    if args.bars_asof > session or (args.bars_asof == session and now < closed):
        raise ValueError("bars-asof includes an incomplete session")
    run_id = args.run_id or snapshot.get("runId", f"{session}-us")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("runId must be a safe filename")
    ratings = read_json(args.ratings)
    if not isinstance(ratings, list):
        raise ValueError("ratings must be a list")
    for rating in ratings:
        if rating.get("decisionId") != f"{run_id}:{rating['ticker']}":
            raise ValueError("rating decisionId must match runId:TICKER; IDs are never rewritten")
    bars, errors = load_bars(args.bars, args.bars_asof)
    quotes = snapshot["quotes"]
    prices = {ticker: quote["last"] for ticker, quote in quotes.items() if "last" in quote}
    market = dict(now=snapshot["now"], sessionDate=session, prices=prices, bars=bars,
                  quotes=quotes, minutesSinceOpen=calendar.minutes_since_open(now),
                  isRegularSession=calendar.is_regular_hours(now))
    tickets = {}
    if log.path.exists():
        for line in log.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["type"] == "risk_verdict" and not event["drill"] and event.get("approvedTicket"):
                ticket = OrderTicket(**event["approvedTicket"])
                tickets[ticket.decisionId] = ticket.to_dict()
                if ticket.decisionId not in state.ticketedDecisionIds:
                    state.reserve(ticket)

    def append(event_type, payload, decision_id=None):
        log.append(event_type, payload, decisionId=decision_id, ts=snapshot["now"])

    def skipped(ticker, reason, source="data"):
        append("reflection_note", dict(prompt="Decision desk skip", text=reason,
                                        ticker=ticker, skipped=True, source=source))

    for event in update(state, state.equity(prices), session, at_close=now >= closed, at_open=now == opened):
        append(event.pop("type"), event)
    if args.graded_calls or args.closed_trades:
        if not args.next_session:
            raise ValueError("step-up evaluation requires --next-session from a trading calendar")
        result = evaluate(read_json(args.graded_calls) if args.graded_calls else [],
                          read_json(args.closed_trades) if args.closed_trades else [],
                          session, args.next_session, at_close=now >= closed, previous=state.stepUp)
        state.stepUp = result["state"]
        append("reflection_note", dict(prompt="Step-up and invalidation", text=result["decision"], evidence=result["evidence"]))
        if result["decision"] == "invalidate":
            append("halt", dict(reason="satellite thesis failed", scope="all", sleeve="satellite"))

    core_dependencies = {t["decisionId"]: [sell["decisionId"] for sell in tickets.values()
                         if sell["sleeve"] == "core" and sell["side"] == "SELL"]
                         for t in tickets.values() if t["sleeve"] == "core" and t["side"] == "BUY"}

    def consider(proposal):
        append("order_intent", {key: proposal[key] for key in
                                ("ticker", "sleeve", "side", "qty", "limitPrice", "sizing", "stop")} |
               dict(notional=proposal["qty"]*proposal["limitPrice"], kind=proposal["kind"], reason=proposal["reason"]),
               proposal["decisionId"])
        risk_state = state
        dependencies = []
        if C.CORE_REBALANCE_AFTER_FILLS and proposal["sleeve"] == "core" and proposal["side"] == "BUY":
            risk_state, dependencies = projected_core_state(state, tickets.values())
        verdict = check(proposal, risk_state, market)
        if dependencies:
            verdict["conditionalOnFullFills"] = dependencies
        ticket = None
        if verdict["verdict"] != "veto":
            ticket = OrderTicket.from_proposal(proposal, verdict, frozen["configHash"], snapshot["now"])
            verdict["approvedTicket"] = ticket.to_dict()
        append("risk_verdict", verdict, proposal["decisionId"])
        if ticket:
            state.reserve(ticket)
            tickets[ticket.decisionId] = ticket.to_dict()
            if dependencies:
                core_dependencies[ticket.decisionId] = dependencies

    exits = propose_exits(state, bars, quotes, session, run_id)
    for ticker, changes in exits["updates"].items():
        state.positions[ticker].update(changes)
    for item in exits["skipped"]:
        skipped(item["ticker"], item["reason"], "exit")
    for proposal in exits["proposals"]:
        consider(proposal)
    try:
        core = propose_core(state, bars, quotes, prices, run_id)
    except (ValueError, KeyError, TypeError) as exc:
        core = []
        append("reflection_note", dict(prompt="Core skip", text=str(exc), skipped=True))
    for proposal in core:
        append("core_rebalance", dict(etf=proposal["ticker"], side=proposal["side"], qty=proposal["qty"], **proposal["sizing"]))
        consider(proposal)
    for rating in ratings:
        ticker = rating["ticker"]
        if ticker not in bars or ticker not in quotes:
            skipped(ticker, errors.get(ticker, "missing cached bars or quote"), "entry")
            continue
        proposal = propose_entry(rating, bars[ticker], quotes[ticker], state.equity(prices), state.tier)
        if proposal["status"] == "skip":
            skipped(ticker, proposal["reason"], "entry")
        else:
            consider(proposal)
    destination = Path(args.tickets_dir) / f"{run_id}.json"
    cancel = [ticket["decisionId"] for ticket in state.pendingTickets
              if ticket["side"] == "BUY" and (state.halted or state.tier == "kill")]
    manifest = dict(runId=run_id, configHash=frozen["configHash"], tickets=list(tickets.values()),
                    coreSellDependencies=core_dependencies,
                    cancelEntryDecisionIds=cancel, executionAuthorized=False,
                    executionNote="Offline risk approval only. Executor must verify prompt freeze, current risk and account, then reconcile fills.")
    atomic_json(destination, manifest)
    atomic_json(args.state, state.to_dict())
    return dict(tickets=str(destination), approved=len(tickets), state=str(args.state))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "ratings", "bars-asof", "log", "quotes"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--bars", default=str(ROOT / ".cache/desk/bars.json"))
    parser.add_argument("--tickets-dir", default=str(ROOT / "tickets"))
    parser.add_argument("--run-id")
    parser.add_argument("--graded-calls")
    parser.add_argument("--closed-trades")
    parser.add_argument("--next-session")
    args = parser.parse_args()
    try:
        print(json.dumps(plan(args)))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"planning refused: {exc}\n")


if __name__ == "__main__":
    main()
