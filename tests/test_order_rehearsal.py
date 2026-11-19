"""Synthetic ten-ticket mornings: real phase scripts, fake transport/clock/broker."""
from argparse import Namespace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from moowoo import calendar, runlock
from moowoo.execution import preflight, prepare, record
from moowoo.ledger import EventLog, verify
from moowoo.persistence import LedgerStore
from moowoo.portfolio import PortfolioState
from moowoo.tickets import OrderTicket
import dispatch_check
import run_session
from hash_prompts import prompt_version
from plan_session import atomic_json, frozen_config
from test_execution import fixture

NOW = datetime.fromisoformat("2026-11-18T15:00:00+00:00")


@pytest.mark.parametrize("stale_second,abort_after_second", [(False, False), (True, False), (True, True)])
def test_ten_order_morning(tmp_path, monkeypatch, stale_second, abort_after_second):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    current = NOW
    lock = dict(holder="test-owner", kind="morning", startedAt=NOW.isoformat(),
                expiresAt=(NOW + timedelta(minutes=45)).isoformat())
    class Clock:
        @staticmethod
        def now(zone): return current
    monkeypatch.setattr(runlock, "datetime", Clock)
    monkeypatch.setattr(dispatch_check, "datetime", Clock)
    monkeypatch.setattr(LedgerStore, "restore", lambda *a: {})
    monkeypatch.setattr(LedgerStore, "fetch", lambda *a: True)
    monkeypatch.setattr(LedgerStore, "remote_lock", lambda *a: lock)
    monkeypatch.setattr(LedgerStore, "save", lambda *a, release=True, **kw: dict(saved=True, unlocked=release))
    monkeypatch.setattr(run_session, "acquire", lambda *a: lock)
    args = Namespace(kind="morning", phase="start", dir=tmp_path, remote=run_session.REMOTE)
    context = run_session.run(args, current)
    inputs, run_id = Path(context["inputs"]), context["runId"]
    state = PortfolioState(cash=100000)
    atomic_json(tmp_path / "state.json", state.to_dict())
    frozen = frozen_config()
    log = EventLog(context["log"], runId=run_id)
    tickets = [OrderTicket(decisionId=f"{run_id}:T{i}", ticker=f"T{i}", side="BUY", qty=50,
        limitPrice=100., sleeve="satellite", kind="drift", stop=94., reason="synthetic rehearsal",
        configHash=frozen["configHash"], createdTs=calendar.utc_stamp(current), estFees=.99, signalAtr=2.)
        for i in range(10)]
    original_invoke = run_session.invoke
    def invoke(script, *arguments):
        if script == "preflight.py":
            prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-18\npromptVersion={prompt_version()}\n"
            preflight(fixture("accounts"), state, frozen, prereg, prompt_version(), [], log)
            return dict(started=True)
        if script == "plan_session.py":
            # Inject ten approved tickets to exercise dispatch independently of sizing/ratings.
            for ticket in tickets: state.reserve(ticket)
            atomic_json(tmp_path / "state.json", state.to_dict())
            atomic_json(tmp_path / f"tickets/{run_id}.json", dict(runId=run_id,
                configHash=frozen["configHash"], tickets=[t.to_dict() for t in tickets]))
            return dict(tickets=len(tickets))
        return original_invoke(script, *arguments)
    monkeypatch.setattr(run_session, "invoke", invoke)
    history = dict(ret_code=0, ret_msg="success", data=dict(orders=[]),
                   pagination=dict(has_more=False, next_key=""))
    for name, payload in dict(history=history, positions=dict(data=[]), cash=dict(cash=100000, equity=100000),
        quotes=dict(now=calendar.utc_stamp(current)), session=dict(barsAsOf="2026-11-17"), responses=[]).items():
        atomic_json(inputs / f"{name}.json", payload)
    for phase in ("preflight", "reconcile", "plan", "prepare"):
        args.phase = phase
        result = run_session.run(args, current)
        assert result["phase"] == ("baseline" if phase == "reconcile" else phase)
    assert len(result["orders"]) == 10
    responses, skipped, submitted = [], [], []
    for index, ticket in enumerate(tickets):
        quote_time = current - timedelta(seconds=61 if stale_second and index == 1 else 0)
        atomic_json(inputs / f"quotes-raw-{ticket.ticker}.json", dict(ret_code=0, ret_msg="success",
            data=dict(snapshot_list=[dict(code="US." + ticket.ticker, update_time=quote_time.timestamp()*1000,
                                         last_price=100, bid_price=99.99, ask_price=100)])))
        check = dispatch_check.run(Namespace(kind="morning", decision_id=ticket.decisionId, dir=tmp_path), current)
        if check.get("retryable"):
            # The second fetched source is still stale: exhaust the quote budget, not an order retry.
            check = dispatch_check.run(Namespace(kind="morning", decision_id=ticket.decisionId, dir=tmp_path), current)
        if check["ok"]:
            assert check["tool"] == "sim_trade_input_order" and type(check["attempt"]) is int
            current += timedelta(seconds=20)  # Inject executor latency, without real waiting/network.
            order_id = str(50000 + index)
            responses.append({key: check[key] for key in ("decisionId", "attempt", "tool", "args")} |
                dict(status="placed", response=dict(ret_code=0, ret_msg="success", data=dict(order_id=order_id))))
            atomic_json(inputs / "responses.json", responses)
            submitted.append(ticket.decisionId)
            history["data"]["orders"].append(dict(order_id=order_id, symbol=ticket.ticker,
                text=ticket.decisionId, side=1, qty="50", price="100", cum_qty="0", avg_fill_price="0", status=1))
            if not abort_after_second:
                args.phase = "record"
                assert run_session.run(args, current)["recorded"] == [ticket.decisionId]
                if index == 0:
                    pending = json.loads((tmp_path / "state.json").read_text())["pendingTickets"]
                    assert len(pending) == 10  # Receipt recording cannot release other prepared tickets.
                before = log.path.read_bytes()
                assert run_session.run(args, current)["recorded"] == []
                assert log.path.read_bytes() == before
        else:
            assert check["skipped"]
            skipped.append(ticket.decisionId)
        if abort_after_second and index == 1: break
    assert len(submitted) == (1 if abort_after_second else 9 if stale_second else 10)
    assert len(skipped) == int(stale_second)
    if not abort_after_second:
        assert (current - NOW).total_seconds() == 20 * len(submitted)
        atomic_json(inputs / "history.json", history)
        args.phase = "reconcile"
        assert not run_session.run(args, current).get("halted")
        args.phase = "finish"
    else:
        # The first saved receipt was deliberately not recorded: abort must recover it.
        args.phase = "abort"
    assert run_session.run(args, current)["unlocked"]
    assert verify(log.path).ok
    saved = PortfolioState.from_dict(json.loads((tmp_path / "state.json").read_text()))
    assert {t["decisionId"] for t in saved.pendingTickets} == set(submitted)
    assert len([e for e in log.read() if e["type"] == "order_submitted"]) == len(submitted)
    # Actual next-day reconcile CLI sees accepted orders from the previous run.
    current = NOW + timedelta(days=1)
    next_log = EventLog(tmp_path / "logs/next-day.jsonl", runId="next-day")
    next_log.append("reflection_note", dict(prompt="rehearsal", text="next-day baseline"))
    atomic_json(inputs / "history.json", history)
    result = original_invoke("reconcile.py", "--runtime", tmp_path, "--log", next_log.path,
        "--state", tmp_path / "state.json", "--history", inputs / "history.json",
        "--positions", inputs / "positions.json", "--cash", inputs / "cash.json")
    assert not result.get("halted")


def test_cumulative_receipts_across_retry_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    ticket = OrderTicket(decisionId="test:AAA", ticker="AAA", side="BUY", qty=50, limitPrice=100.,
        sleeve="satellite", kind="drift", stop=94., reason="test", configHash="a"*64,
        createdTs=calendar.utc_stamp(NOW), estFees=.99)
    tickets = {ticket.decisionId: ticket}
    log = EventLog(tmp_path / "test.jsonl", runId="test")
    first = prepare(tickets, log)["orders"][0] | dict(status="rejected", reason="synthetic rejection")
    record(tickets, [first], log)
    second = prepare(tickets, log)["orders"][0] | dict(status="placed", response=fixture("placement"))
    second.pop("tool")  # Executor placement contract permits omitting the tool field.
    assert record(tickets, [first, second], log)["recorded"] == [ticket.decisionId]
    before = log.path.read_bytes()
    assert record(tickets, [first, second], log)["recorded"] == []
    assert log.path.read_bytes() == before
