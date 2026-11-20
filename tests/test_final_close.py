"""Final-close and absolute ticker-cap regressions; all broker replies are synthetic."""
from argparse import Namespace
from datetime import datetime, timedelta
import json

import pytest

from moowoo import calendar, config as C
from moowoo.execution import preflight, prepare, reconcile
from moowoo.exits import propose_exits
from moowoo.fees import estimate_fees
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.risk import check
from moowoo.tickets import OrderTicket
from hash_prompts import prompt_version
from plan_session import atomic_json, frozen_config, plan
from test_execution import fixture
from test_risk_desk import desk, position, bars
from test_runtime_guards import prepared, RUN
import dispatch_check
import reconcile as reconcile_cli
import run_session
import watch


def stamp(time):
    return f"2026-11-27T{time}:00-05:00"


def holdings():
    return {"IEF": position("core", qty=30),
            "SPY": position("beta", sleeve="beta", qty=40),
            "AAA": position(qty=20, entryDate=C.FINAL_DAY),
            "BBB": position("bounce", qty=10, entryDate=C.FINAL_DAY)}


def watch_tick(tmp_path, state, time, run="watch", halt=None):
    now = stamp(time)
    atomic_json(tmp_path / "state.json", state.to_dict())
    atomic_json(tmp_path / "bars.json", {t: [dict(date="2026-11-25", open=100,
        high=101, low=99, close=100, volume=100000)] for t in state.positions})
    atomic_json(tmp_path / "quotes.json", dict(now=now, sessionDate=C.FINAL_DAY,
        quotes={t: dict(last=100, bid=100, ask=100.01, ts=now) for t in state.positions}))
    log = EventLog(tmp_path / f"{run}.jsonl", runId=run)
    if halt:
        log.append("halt", dict(reason=halt, scope="all"))
    result = watch.run(Namespace(state=tmp_path / "state.json", bars=tmp_path / "bars.json",
        quotes=tmp_path / "quotes.json", bars_asof="2026-11-25", tickets_dir=tmp_path / "tickets"), log)
    return json.loads(open(result["tickets"]).read()), log


def test_1159_no_final_liquidation(tmp_path):
    manifest, _ = watch_tick(tmp_path, PortfolioState(cash=90000, positions=holdings()), "11:59")
    assert manifest["tickets"] == []


@pytest.mark.parametrize("gate", ["normal", "reduced", "exits_only", "kill", "daily_loss"])
def test_noon_all_sleeves_net_pending_sells_despite_risk_halts(tmp_path, gate):
    state = PortfolioState(cash=90000, positions=holdings())
    halt = None
    if gate == "daily_loss":
        state.dailyLossHalted = True
        halt = "daily loss limit"
    else:
        state.tier = gate
        if gate == "kill":
            state.halted, state.haltReason = True, "peak drawdown kill"
            halt = state.haltReason
    state.pendingTickets = [dict(decisionId="old:IEF", ticker="IEF", side="SELL", qty=7),
                            dict(decisionId="old:CCC", ticker="CCC", side="BUY", qty=5)]
    manifest, _ = watch_tick(tmp_path, state, "12:00", halt=halt)
    tickets = manifest["tickets"]
    assert {t["ticker"]: t["qty"] for t in tickets} == dict(IEF=23, SPY=40, AAA=20, BBB=10)
    assert all(t["side"] == "SELL" and t["reason"] == "final liquidation" for t in tickets)
    assert all(t["limitPrice"] == 99 for t in tickets)
    assert manifest["cancelEntryDecisionIds"] == ["old:CCC"]


@pytest.mark.parametrize("time", ["09:35", "12:00"])
@pytest.mark.parametrize("gate", ["normal", "daily_loss", "reduced", "exits_only", "kill"])
def test_final_morning_no_buys_and_no_duplicate_rebalance(tmp_path, desk, time, gate):
    _, state, market = desk
    state.positions = holdings()
    state.cash = 90000
    state.sessionDate = C.FINAL_DAY
    if gate == "daily_loss":
        state.cash = 88000  # Trigger a new daily-loss event without a peak-drawdown tier.
        state.peakEquity = 98000
    else:
        state.tier = gate
    run = "morning"
    atomic_json(tmp_path / "state.json", state.to_dict())
    atomic_json(tmp_path / "ratings.json", [dict(ticker="CCC", decisionId="morning:CCC",
        confidence=1, tier="single", **{"class": "explained_up"})])
    atomic_json(tmp_path / "bars.json", {t: [dict(date=str(day.date()), **row.to_dict())
        for day, row in bars(i+1, end="2026-11-25").iterrows()]
        for i, t in enumerate(market["bars"])})
    atomic_json(tmp_path / "quotes.json", dict(now=stamp(time), sessionDate=C.FINAL_DAY,
        quotes={t: q | dict(ts=stamp(time)) for t, q in market["quotes"].items()}))
    result = plan(Namespace(state=tmp_path / "state.json", ratings=tmp_path / "ratings.json",
        bars=tmp_path / "bars.json", quotes=tmp_path / "quotes.json", bars_asof="2026-11-25",
        log=tmp_path / "morning.jsonl", tickets_dir=tmp_path / "tickets", run_id=run,
        graded_calls=None, closed_trades=None, next_session=None))
    tickets = json.loads(open(result["tickets"]).read())["tickets"]
    assert all(t["side"] == "SELL" for t in tickets)
    if time == "12:00":
        assert len(tickets) == 4
        assert all(t["reason"] == "final liquidation" for t in tickets)


@pytest.mark.parametrize("ticker,kind,sleeve", [("IEF", "core", "core"),
    ("SPY", "beta", "beta"), ("AAA", "drift", "satellite")])
@pytest.mark.parametrize("held,expected", [(350, 30), (380, 0), (410, 0)])
def test_absolute_cap_shrink_drop_counts_pending_at_ticket_limit(desk, ticker, kind, sleeve, held, expected):
    proposal, state, market = desk
    state.cash = 300000
    state.positions[ticker] = position(kind, qty=held, sleeve=sleeve)
    state.pendingTickets = [dict(decisionId="old:buy", ticker=ticker, side="BUY", qty=20,
        limitPrice=80, sleeve=sleeve, kind=kind, estFees=.99),
        dict(decisionId="old:sell", ticker=ticker, side="SELL", qty=50,
        limitPrice=99, sleeve=sleeve, kind=kind, estFees=.99)]
    proposal.update(ticker=ticker, kind=kind, sleeve=sleeve, qty=100)
    result = check(proposal, state, market)
    assert result["qtyAfter"] == expected
    assert result["firedRule"] == "ticker_cap"
    assert result["verdict"] == ("resize" if expected else "veto")


def test_core_projection_does_not_free_ticker_cap(desk):
    from moowoo.core import projected_core_state
    proposal, state, market = desk
    state.cash = 300000
    state.positions["IEF"] = position("core", qty=400)
    projected, _ = projected_core_state(state, [dict(ticker="IEF", sleeve="core", side="SELL",
        qty=100, limitPrice=100, estFees=.99, decisionId="old:IEF")])
    proposal.update(ticker="IEF", sleeve="core", kind="core")
    assert check(proposal, projected, market, ticker_state=state)["qtyAfter"] == 0


def test_partial_fill_1230_cancel_then_retry_1255(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    state = PortfolioState(cash=96000, positions={"SPY": position("beta", sleeve="beta", qty=40)},
                           sessionDate=C.FINAL_DAY)
    manifest, log = watch_tick(tmp_path, state, "12:00", run="noon")
    ticket = OrderTicket(**manifest["tickets"][0])
    state.reserve(ticket)
    log.append("order_submitted", dict(ticker="SPY", orderId="paper-sell", qty=40,
        limitPrice=ticket.limitPrice, trdEnv="SIMULATE"), decisionId=ticket.decisionId)
    history = [dict(orderId="paper-sell", decisionId=ticket.decisionId, ticker="SPY", side="SELL",
        qty=40, limitPrice=ticket.limitPrice, filledQty=15, avgPrice=100, status=1)]
    cash = dict(cash=97500-estimate_fees("SELL", 15), equity=100000-estimate_fees("SELL", 15))
    positions = [dict(ticker="SPY", qty=25, avgCost=100, marketPrice=100,
                      decisionId=state.positions["SPY"]["decisionId"])]
    state, result = reconcile({ticket.decisionId: ticket}, history, positions, cash, state, log,
                              now=stamp("12:30"))
    assert result["diff"] == {} and result["cancel"][0]["remainingQty"] == 25
    assert not propose_exits(state, {}, {"SPY": dict(bid=100)}, C.FINAL_DAY, "half",
                             now=stamp("12:30"))["proposals"]
    # Record the real-shaped cancellation through the reconciliation script entry point.
    atomic_json(tmp_path / "state.json", state.to_dict())
    atomic_json(tmp_path / "cancel-responses.json", [dict(decisionId=ticket.decisionId,
        tool="sim_trade_cancel_order", args=dict(acc_id="synthetic-paper-account", market=100,
        order_id="paper-sell"), response=dict(ret_code=0, ret_msg="success",
        data=dict(order_id="paper-sell")))])
    atomic_json(tmp_path / "history.json", dict(ret_code=0, ret_msg="success", data=dict(orders=[dict(
        order_id="paper-sell", symbol="US.SPY", text=ticket.decisionId, side=2, qty=40,
        price=ticket.limitPrice, cum_qty=15, avg_fill_price=100, status=5)]),
        pagination=dict(has_more=False, next_key="")))
    atomic_json(tmp_path / "positions.json", dict(ret_code=0, ret_msg="success", data=dict(positions=[dict(
        symbol="US.SPY", qty=25, cost_price=100, cur_price=100, text=positions[0]["decisionId"])])))
    atomic_json(tmp_path / "cash.json", dict(ret_code=0, ret_msg="success", data=dict(
        balance=cash["cash"], total_asset=cash["equity"], hold=0)))
    call = Namespace(tickets=tmp_path / "tickets/noon.json", state=tmp_path / "state.json",
        history=tmp_path / "history.json", positions=tmp_path / "positions.json",
        cash=tmp_path / "cash.json", cancel_responses=tmp_path / "cancel-responses.json")
    assert reconcile_cli.run(call, log)["diff"] == {}
    assert reconcile_cli.run(call, log)["diff"] == {}  # Receipt recording is idempotent.
    state = PortfolioState.from_dict(json.loads((tmp_path / "state.json").read_text()))
    assert not state.pendingTickets
    retry, _ = watch_tick(tmp_path, state, "12:55", run="last")
    assert [(t["ticker"], t["qty"], t["limitPrice"]) for t in retry["tickets"]] == [("SPY", 25, 99)]


@pytest.mark.parametrize("reason", ["daily loss limit", "peak drawdown kill", "unexplained broker/book difference"])
def test_final_dispatch_halt_exception_and_1255_marketability(prepared, reason):
    args, _, log, _, lock = prepared
    now = datetime.fromisoformat(stamp("12:55"))
    lock.update(startedAt=now.isoformat(), expiresAt=(now+timedelta(minutes=5)).isoformat())
    ticket = OrderTicket(decisionId=RUN+":SPY", ticker="SPY", side="SELL", qty=25, limitPrice=99,
        sleeve="beta", kind="beta", stop=0, reason="final liquidation",
        configHash=frozen_config()["configHash"], createdTs=calendar.utc_stamp(now), estFees=estimate_fees("SELL", 25))
    log.append("halt", dict(reason=reason, scope="all"))
    atomic_json(args.dir / f"tickets/{RUN}.json", dict(runId=RUN, configHash=ticket.configHash,
        tickets=[ticket.to_dict()]))
    atomic_json(args.dir / f"receipts/{RUN}/prepare-final.json", prepare({ticket.decisionId: ticket}, log))
    atomic_json(args.dir / f"inputs/{RUN}/quotes-raw-SPY.json", dict(ret_code=0, ret_msg="success",
        data=dict(snapshot_list=[dict(code="US.SPY", update_time=now.timestamp()*1000,
            last_price=99.50, bid_price=99.50, ask_price=99.51)])))
    args.decision_id = ticket.decisionId
    if reason.startswith("unexplained"):
        with pytest.raises(ValueError, match="halted"):
            dispatch_check.run(args, now)
    else:
        result = dispatch_check.run(args, now)
        assert result["ok"] and result["args"]["price"] == "99.00"


@pytest.mark.parametrize("kill", [False, True])
def test_preflight_final_risk_halt_exception(tmp_path, monkeypatch, kill):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    frozen = frozen_config()
    prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-20\npromptVersion={prompt_version()}\n"
    state = PortfolioState(cash=90000, tier="kill" if kill else "normal", halted=kill,
        haltReason="peak drawdown kill" if kill else "", dailyLossHalted=True)
    log = EventLog(tmp_path / "preflight.jsonl", runId="final")
    log.append("halt", dict(reason="peak drawdown kill" if kill else "daily loss limit", scope="all"))
    preflight(fixture("accounts"), state, frozen, prereg, prompt_version(), [], log, now=stamp("12:00"))
    assert log.read()[-1]["type"] == "run_started"


def test_calendar_stops_liquidation_at_early_close():
    assert calendar.is_final_liquidation(stamp("12:55"))
    assert not calendar.run_allowed("watch", stamp("13:00"))
    assert not calendar.is_final_liquidation(stamp("13:00"))


def test_runner_repeats_baseline_with_cancel_receipts(prepared, monkeypatch):
    args, _, log, _, _ = prepared
    atomic_json(args.dir / ".session.json", dict(kind="morning", runId=RUN, holder="owner", phase="baseline"))
    inputs = args.dir / "inputs" / RUN
    atomic_json(inputs / "cancel-responses.json", [])
    invoked = []
    monkeypatch.setattr(run_session, "invoke", lambda *args: invoked.append(args) or dict(diff={}, cancel=[]))
    from test_runtime_guards import NOW
    result = run_session.run(Namespace(kind="morning", phase="reconcile", dir=args.dir,
        remote=run_session.REMOTE), NOW)
    assert "--cancel-responses" in invoked[0]
    assert json.loads((args.dir / ".session.json").read_text())["phase"] == "baseline"


def test_final_limit_rounds_down_and_keeps_ordinary_pricing():
    from moowoo.desk_data import limit_price
    quote = dict(bid=100.03, last=100.05)
    assert limit_price(quote, "SELL") == 100.03
    assert limit_price(quote, "SELL", final_liquidation=True) == 99.02
    assert limit_price(dict(bid=None, last=100), "SELL", final_liquidation=True) == 99
