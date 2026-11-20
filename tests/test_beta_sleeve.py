"""SLEEVE-01 and the 19 Nov cash-funded core rebalance, entirely offline."""
from argparse import Namespace
import json
import subprocess
import sys

import pytest

from moowoo import config as C
from moowoo.broker import snapshot_to_state
from moowoo.core import propose_beta, require_core_fills
from moowoo.execution import prepare, reconcile
from moowoo.exits import propose_exits
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.risk import check
from moowoo.tickets import OrderTicket
from plan_session import atomic_json, frozen_config
from reconcile import RuntimeLogs
from export_dashboard import export
from test_risk_desk import desk, position, NOW
from test_runtime_guards import prepared
import dispatch_check
import watch


def beta_ticket(qty=299, decision="run:SPY"):
    return OrderTicket(decisionId=decision, ticker="SPY", side="BUY", qty=qty,
        limitPrice=100, sleeve="beta", kind="beta", stop=0, reason="SPY rebalance",
        configHash=frozen_config()["configHash"], createdTs=NOW, estFees=.99)


def test_beta_target_with_ample_cash(desk):
    _, state, market = desk
    proposal, = propose_beta(state, market["quotes"], market["prices"], "run")
    assert proposal["sizing"]["targetWeight"] == .30 and proposal["qty"] == 300
    verdict = check(proposal, state, market)
    ticket = OrderTicket.from_proposal(proposal, verdict, frozen_config()["configHash"], NOW)
    assert ticket.qty == 298  # Whole shares at the cushioned limit keep the target after the flat fee.
    assert ticket.sleeve == ticket.kind == "beta" and ticket.stop == 0


def test_beta_takes_only_cash_left_after_satellite_reservations(desk):
    proposal, state, market = desk
    state.cash = 60000
    state.positions["IEF"] = position("core", qty=300)
    state.positions["BBB"] = position(qty=100)
    # Two independent approved stock reservations take 40% of equity.
    for ticker in ("AAA", "CCC"):
        state.reserve(OrderTicket.from_proposal(proposal | dict(ticker=ticker,
            decisionId=f"run:{ticker}", qty=200), dict(verdict="approve", ticker=ticker, qtyAfter=200),
            frozen_config()["configHash"], NOW))
    beta, = propose_beta(state, market["quotes"], market["prices"], "run")
    assert beta["side"] == "BUY" and beta["qty"] == 99
    verdict = check(beta, state, market)
    assert verdict["qtyAfter"] == 99
    state.reserve(OrderTicket.from_proposal(beta, verdict, frozen_config()["configHash"], NOW))
    assert state.cash-state.reservedCash >= C.CASH_FLOOR*state.equity(market["prices"])


def test_satellite_cash_shortfall_never_sells_spy(desk):
    proposal, state, market = desk
    state.cash = 10000
    state.positions = {"SPY": position("beta", sleeve="beta", qty=300),
                       "IEF": position("core", qty=300), "BBB": position(qty=300)}
    assert check(proposal, state, market)["firedRule"] == "cash_floor"
    assert propose_beta(state, market["quotes"], market["prices"], "run") == []
    beta_only = PortfolioState(cash=70000, positions={"SPY": state.positions["SPY"]})
    assert propose_exits(beta_only, {}, {}, "2026-11-27", "watch")["proposals"] == []


@pytest.mark.parametrize("qty,expected", [(350, None), (375, 75), (400, 100)])
def test_beta_trim_uses_core_band(desk, qty, expected):
    _, state, market = desk
    state.cash = 100000-qty*100
    state.positions["SPY"] = position("beta", sleeve="beta", qty=qty)
    proposals = propose_beta(state, market["quotes"], market["prices"], "run")
    if expected is None:
        assert proposals == []
    else:
        sell, = proposals
        assert sell["side"] == "SELL" and sell["qty"] == expected
        state.reserve(sell)
        assert propose_beta(state, market["quotes"], market["prices"], "run")[0]["qty"] <= qty-expected


@pytest.mark.parametrize("gate", ["kill", "exits_only", "halted", "daily_loss", "final_day", "reduced"])
def test_beta_risk_matches_core(desk, gate):
    _, state, market = desk
    proposal, = propose_beta(state, market["quotes"], market["prices"], "run")
    if gate in ("kill", "exits_only", "reduced"):
        state.tier = gate
    elif gate == "halted":
        state.halted = True
    elif gate == "daily_loss":
        state.dailyLossHalted = True
    else:
        market["sessionDate"] = C.FINAL_DAY
    beta = check(proposal, state, market)
    core = check(proposal | dict(ticker="XLV", sleeve="core", kind="core"), state, market)
    assert beta["verdict"] == core["verdict"]
    assert beta["verdict"] == ("resize" if gate == "reduced" else "veto")


@pytest.mark.parametrize("sleeve,kind,ticker", [("satellite", "drift", "SPY"), ("core", "core", "SPY"), ("beta", "beta", "AAA")])
def test_spy_only_orderable_as_beta(desk, sleeve, kind, ticker):
    proposal, state, market = desk
    with pytest.raises(ValueError):
        check(proposal | dict(ticker=ticker, sleeve=sleeve, kind=kind), state, market)
    payload = beta_ticket().to_dict() | dict(ticker=ticker, sleeve=sleeve, kind=kind, ticketHash="")
    with pytest.raises(ValueError):
        OrderTicket(**payload)


@pytest.mark.parametrize("filled", [0, 40, 85])
def test_nov19_core_buys_authorized_with_unfilled_ief(tmp_path, filled):
    # 66% cash, 23% held core, 11% stock; buy 13% core while SELL 85 IEF is pending.
    state = PortfolioState(cash=66000+filled*100, positions={
        "IEF": position("core", qty=150-filled), "XLP": position("core", qty=80),
        "AAA": position(qty=110)})
    buys = [OrderTicket(decisionId=f"run:{ticker}", ticker=ticker, side="BUY", qty=qty,
        limitPrice=100, sleeve="core", kind="core", stop=0, reason="rebalance",
        configHash=frozen_config()["configHash"], createdTs=NOW, estFees=.99)
        for ticker, qty in (("USMV", 50), ("XLV", 40), ("GLD", 40))]
    sell = buys[0].to_dict() | dict(decisionId="run:IEF", ticker="IEF", side="SELL", qty=85)
    for ticket in buys:
        state.reserve(ticket)
    if filled < 85:
        state.reserve(sell | dict(qty=85-filled))
    manifest = dict(tickets=[sell, *(t.to_dict() for t in buys)],
        coreSellDependencies={t.decisionId: [sell["decisionId"]] for t in buys})
    log = EventLog(tmp_path / "core.jsonl", runId="run")
    log.append("order_submitted", dict(ticker="IEF", orderId="paper-ief", qty=85,
        limitPrice=100, trdEnv="SIMULATE"), decisionId="run:IEF")
    state.execution = dict(fills={"paper-ief": dict(filledQty=filled)})
    before = state.to_dict()
    for ticket in buys:
        require_core_fills(ticket, manifest, state, log, {"IEF": 100, "XLP": 100, "AAA": 100})
    assert state.to_dict() == before


def test_spy_fills_and_topups_reconcile_as_beta(tmp_path):
    first = EventLog(tmp_path / "first.jsonl", runId="run0")
    second = EventLog(tmp_path / "second.jsonl", runId="run1")
    log = RuntimeLogs([first], second)
    state = PortfolioState(cash=100000)
    tickets, history = {}, []
    for index, qty in enumerate((200, 99)):
        ticket = beta_ticket(qty, f"run{index}:SPY")
        tickets[ticket.decisionId] = ticket
        state.reserve(ticket)
        order_id = f"paper-spy-{index}"
        log.append("order_submitted", dict(ticker="SPY", orderId=order_id, qty=qty,
            limitPrice=100, trdEnv="SIMULATE"), decisionId=ticket.decisionId)
        history.append(dict(orderId=order_id, decisionId=ticket.decisionId, ticker="SPY", side="BUY",
            qty=qty, limitPrice=100, filledQty=qty, avgPrice=100, status=2))
        total = sum(row["qty"] for row in history)
        positions = [dict(ticker="SPY", qty=total, avgCost=100, marketPrice=100,
                          decisionId=ticket.decisionId)]
        cash = dict(cash=100000-total*100-(index+1)*.99, equity=100000-(index+1)*.99)
        state, result = reconcile(tickets, history, positions, cash, state, log)
        assert result["diff"] == {} and not result["halted"]
        assert state.positions["SPY"]["sleeve"] == state.positions["SPY"]["kind"] == "beta"
        assert state.positions["SPY"]["qty"] == total
        state, again = reconcile(tickets, history, positions, cash, state, log)
        assert again["diff"] == {} and state.positions["SPY"]["qty"] == total
    with pytest.raises(ValueError, match="unmatched strategy identity"):
        snapshot_to_state([positions[0] | dict(decisionId="unknown")], cash, state)


@pytest.mark.parametrize("constraint", [None, "kill", "exits_only", "daily_loss", "cash"])
def test_beta_real_dispatch(prepared, constraint):
    from test_runtime_guards import RUN, NOW as dispatch_now
    args, _, log, _, _ = prepared
    ticket = beta_ticket(50, RUN+":SPY")
    state = PortfolioState(cash=100000)
    if constraint in ("kill", "exits_only"):
        state.tier = constraint
    elif constraint == "daily_loss":
        state.dailyLossHalted = True
    elif constraint == "cash":
        state.cash = 12000
        state.positions["IEF"] = position("core", qty=880, marketPrice=100)
    state.reserve(ticket)
    atomic_json(args.dir / "state.json", state.to_dict())
    atomic_json(args.dir / f"tickets/{RUN}.json", dict(runId=RUN, configHash=ticket.configHash,
        tickets=[ticket.to_dict()]))
    result = prepare({ticket.decisionId: ticket}, log)
    atomic_json(args.dir / f"receipts/{RUN}/prepare-beta.json", result)
    atomic_json(args.dir / f"inputs/{RUN}/quotes-raw-SPY.json", dict(ret_code=0, ret_msg="success",
        data=dict(snapshot_list=[dict(code="US.SPY", update_time=dispatch_now.timestamp()*1000,
            last_price=100, bid_price=99.99, ask_price=100)])))
    args.decision_id = ticket.decisionId
    result = dispatch_check.run(args, dispatch_now)
    assert result["ok"] is (constraint is None)


@pytest.mark.parametrize("kill", [False, True])
def test_beta_through_watcher_entrypoint(tmp_path, kill):
    state = PortfolioState(cash=70000, positions={"SPY": position("beta", sleeve="beta", qty=300)},
                           tier="kill" if kill else "normal")
    atomic_json(tmp_path / "state.json", state.to_dict())
    atomic_json(tmp_path / "bars.json", {})
    atomic_json(tmp_path / "quotes.json", dict(now=NOW, sessionDate="2026-11-17",
        quotes={"SPY": dict(last=100, bid=99.95, ask=100, ts=NOW)} if kill else {}))
    log = EventLog(tmp_path / "watch.jsonl", runId="watch")
    args = Namespace(state=tmp_path / "state.json", bars=tmp_path / "bars.json",
        quotes=tmp_path / "quotes.json", bars_asof="2026-11-16", tickets_dir=tmp_path / "tickets")
    result = watch.run(args, log)
    tickets = json.loads(open(result["tickets"]).read())["tickets"]
    assert len(tickets) == int(kill)
    if kill:
        assert tickets[0]["sleeve"] == "beta" and tickets[0]["side"] == "SELL"


def test_dashboard_export_preserves_beta(tmp_path):
    runtime = tmp_path / "runtime"
    run = "2026-11-20-morning-abc"
    log = EventLog(runtime / f"logs/{run}.jsonl", runId=run)
    log.append("order_intent", dict(ticker="SPY", sleeve="beta", kind="beta", side="BUY",
        qty=50, limitPrice=100, notional=5000, stop=0, sizing={}), decisionId=run+":SPY")
    out = tmp_path / "feed"
    export(None, None, out, runtime=runtime)
    row = json.loads((out / f"{run}.jsonl").read_text())
    assert row["sleeve"] == "beta" and row["ticker"] == "SPY"

@pytest.mark.parametrize("stock_count", [0, 2])
def test_morning_cli_prioritizes_stocks_then_spy(desk, tmp_path, stock_count):
    from moowoo.core import weights
    _, state, market = desk
    for ticker in ("AAA", "CCC"):
        frame = market["bars"][ticker]
        frame.loc[:, ["open", "high", "low", "close"]] *= 100 / frame.close.iloc[-1]
        frame.loc[frame.index[-1], "volume"] = 4_200_000
    state.positions = {ticker: position("core", qty=int(weight*1000), decisionId=f"old:{ticker}")
                       for ticker, weight in weights(market["bars"]).items()}
    state.positions["BBB"] = position(qty=100)
    state.cash = 100000-sum(p["qty"]*100 for p in state.positions.values())
    run = "2026-11-17-priority"
    ratings = [dict(ticker=ticker, decisionId=f"{run}:{ticker}", confidence=1,
                    tier="single", **{"class": "explained_up"})
               for ticker in ("AAA", "CCC")[:stock_count]]
    payloads = dict(state=state.to_dict(), ratings=ratings,
        bars={ticker: [dict(date=str(day.date()), **row.to_dict()) for day, row in frame.iterrows()]
              for ticker, frame in market["bars"].items()},
        quotes=dict(now=NOW, sessionDate="2026-11-17", quotes=market["quotes"]))
    for name, value in payloads.items():
        atomic_json(tmp_path / f"{name}.json", value)
    command = [sys.executable, "scripts/plan_session.py", "--run-id", run,
        "--bars-asof", "2026-11-16", "--log", str(tmp_path / "plan.jsonl"),
        "--tickets-dir", str(tmp_path / "tickets")]
    for name in payloads:
        command += ["--"+name, str(tmp_path / f"{name}.json")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / f"tickets/{run}.json").read_text())
    tickets = manifest["tickets"]
    assert [t["ticker"] for t in tickets] == [r["ticker"] for r in ratings]+["SPY"]
    assert tickets[-1]["sleeve"] == "beta"
    if stock_count == 0:
        assert tickets[-1]["qty"] == 298
    else:
        assert 90 <= tickets[-1]["qty"] <= 110
    saved = PortfolioState.from_dict(json.loads((tmp_path / "state.json").read_text()))
    assert saved.cash == state.cash
    assert saved.cash-saved.reservedCash >= C.CASH_FLOOR*saved.equity(market["prices"])
