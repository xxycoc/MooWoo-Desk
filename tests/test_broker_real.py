"""Captured envelopes plus explicitly synthetic edge cases; no broker calls."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo.broker import parse_history, parse_placement
from moowoo.execution import prepare, record, reconcile
from moowoo.fees import estimate_fees
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.tickets import OrderTicket, to_sim_order, verify_placed


ROOT = Path(__file__).resolve().parents[1]
RUN = "2026-11-17-us"


def sample(name):
    return json.loads((ROOT / f"fixtures/broker/real_sim_trade_{name}.json").read_text())["response"]


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "<ORDINARY_PAPER_ACC>")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    frozen = json.loads((ROOT / "config/frozen-2026-11-17.json").read_text())
    ticket = OrderTicket(decisionId=RUN+":AAPL", ticker="AAPL", side="BUY", qty=1,
        limitPrice=353.80, sleeve="satellite", kind="drift", stop=340, reason="test",
        configHash=frozen["configHash"], createdTs="2026-11-17T15:00:00Z", estFees=.99)
    return ticket, EventLog(tmp_path / f"{RUN}.jsonl"), PortfolioState(cash=100000)


def placed(context):
    ticket, log, state = context
    state.reserve(ticket)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    record(tickets, [request | dict(status="placed", response=sample("input_order"))], log)
    return ticket, log, state


def test_order_arguments_and_numeric_verification(context):
    ticket, _, _ = context
    args = to_sim_order(ticket)
    assert args["qty"] == "1" and args["price"] == "353.80"
    assert type(args["order_trade_time_type"]) is int and args["order_trade_time_type"] == 1
    assert verify_placed(ticket, args | dict(qty="1.0", price="353.8"))["ok"]
    for changes in (dict(price="353.81"), dict(qty="2"), dict(price="NaN"),
                    dict(qty=True), dict(order_trade_time_type=1.0), dict(order_trade_time_type=2)):
        assert not verify_placed(ticket, args | changes)["ok"]


def test_real_history_unfilled_no_fill_or_halt(context):
    ticket, log, state = placed(context)
    history = parse_history(sample("history_order_list_unfilled"))
    row = history[0]
    assert row["filledQty"] == 0 and row["fillState"] == "unfilled"
    assert row["ticker"] == "AAPL" and row["internalMarket"] == 2
    assert row["createTime"] == 1794890280000000
    updated, result = reconcile({ticket.decisionId: ticket}, history, [],
        dict(cash=100000, equity=100000), state, log)
    assert not result["halted"] and not result["diff"]
    assert updated.cash == 100000 and not updated.positions
    assert not any(event["type"] in ("fill", "halt") for event in log.read())


@pytest.mark.parametrize("status", [2, 999])
@pytest.mark.parametrize("quantity,outcome", [(0, "unfilled"), (1, "partial"), (2, "filled")])
def test_fill_state_ignores_status(context, status, quantity, outcome):
    ticket, log, state = context
    ticket = OrderTicket(**(ticket.body() | dict(qty=2, estFees=estimate_fees("BUY", 2))))
    ticket, log, state = placed((ticket, log, state))
    payload = sample("history_order_list_unfilled")
    payload["data"]["orders"][0].update(qty="2", cum_qty=str(quantity),
        avg_fill_price="353.8" if quantity else "0", status=status)
    history = parse_history(payload)
    assert history[0]["fillState"] == outcome
    assert history[0]["terminal"] == (quantity == 2)
    positions = [dict(ticker="AAPL", qty=quantity, avgCost=353.8, marketPrice=353.8)] if quantity else []
    fees = estimate_fees("BUY", quantity)
    updated, result = reconcile({ticket.decisionId: ticket}, history, positions,
        dict(cash=100000-quantity*353.8-fees, equity=100000-fees), state, log)
    assert not result["halted"]
    assert bool(updated.pendingTickets) == (quantity < 2)


def test_history_pagination(context):
    first = sample("history_order_list_unfilled")
    second = deepcopy(first)
    second["data"]["orders"][0]["order_id"] = "another-test-order"
    first["pagination"] = dict(has_more=True, next_key="cursor-2")
    requested = []
    def fetch(cursor):
        requested.append(cursor)
        return second
    assert len(parse_history(first, fetch)) == 2
    assert requested == ["cursor-2"]
    with pytest.raises(ValueError, match="incomplete"):
        parse_history(first)
    with pytest.raises(ValueError, match="repeated"):
        parse_history(first, lambda cursor: first)
    with pytest.raises(ValueError, match="broker ret_code"):
        parse_history(first, lambda cursor: dict(ret_code=3, ret_msg="page failed"))
    second["data"]["orders"][0]["order_id"] = first["data"]["orders"][0]["order_id"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_history(first, fetch)


@pytest.mark.parametrize("field", ["ret_code", "ret_msg", "data", "pagination"])
def test_missing_envelope_fields(context, field):
    payload = sample("history_order_list_unfilled")
    del payload[field]
    with pytest.raises(ValueError, match="required"):
        parse_history(payload)


@pytest.mark.parametrize("payload", [{"order_id": "old-shape"},
    {"ret_code": 0, "ret_msg": "success", "data": {}},
    {"ret_code": False, "ret_msg": "success", "data": {"order_id": "test"}}])
def test_invalid_placement_envelopes(payload):
    with pytest.raises(ValueError):
        parse_placement(payload)


@pytest.mark.parametrize("field", ["qty", "cum_qty", "avg_fill_price", "order_id", "side", "status", "text"])
def test_missing_history_fields_fail_closed(context, field):
    payload = sample("history_order_list_unfilled")
    del payload["data"]["orders"][0][field]
    with pytest.raises(ValueError, match="required"):
        parse_history(payload)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0.5", True])
def test_invalid_fill_quantities_fail_closed(context, value):
    payload = sample("history_order_list_unfilled")
    payload["data"]["orders"][0]["cum_qty"] = value
    with pytest.raises(ValueError):
        parse_history(payload)


def test_failed_placement_logs_broker_message(context):
    ticket, log, _ = context
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    failure = dict(ret_code=7, ret_msg="test placement refused")
    with pytest.raises(ValueError, match="test placement refused"):
        parse_placement(failure)
    record(tickets, [request | dict(status="placed", response=failure)], log)
    assert log.read()[-1]["reason"] == "test placement refused"
    assert not any(event["type"] == "order_submitted" for event in log.read())


@pytest.mark.parametrize("code", [0, 9])
def test_cancellation_requires_logged_success(context, code):
    ticket, log, state = placed(context)
    tickets = {ticket.decisionId: ticket}
    receipt = dict(decisionId=ticket.decisionId, tool="sim_trade_cancel_order",
        args=dict(acc_id="<ORDINARY_PAPER_ACC>", market=100, order_id="3164623"),
        response=dict(ret_code=code, ret_msg="synthetic cancellation"))
    record(tickets, [receipt], log)
    updated, result = reconcile(tickets, parse_history(sample("history_order_list_unfilled")),
        [], dict(cash=100000, equity=100000), state, log)
    assert bool(updated.pendingTickets) == (code != 0)
    assert bool(result["cancel"]) == (code != 0)


def test_matching_order_id_still_checks_trade_details(context):
    ticket, log, state = placed(context)
    payload = sample("history_order_list_unfilled")
    payload["data"]["orders"][0]["price"] = "353.81"
    with pytest.raises(ValueError, match="limitPrice"):
        reconcile({ticket.decisionId: ticket}, parse_history(payload), [],
                  dict(cash=100000, equity=100000), state, log)


def test_record_and_reconcile_commands(context, tmp_path):
    ticket, log, state = context
    sys.path.insert(0, str(ROOT / "scripts"))
    from hash_prompts import prompt_version
    log.append("run_started", dict(configHash=ticket.configHash, promptVersion=prompt_version(),
        trdEnv="SIMULATE", tier="normal", equity=100000, cash=100000, universe=["AAPL"]))
    state.reserve(ticket)
    request = prepare({ticket.decisionId: ticket}, log)["orders"][0]
    files = dict(tickets=dict(runId=RUN, configHash=ticket.configHash, tickets=[ticket.to_dict()]),
        responses=[request | dict(status="placed", response=sample("input_order"))],
        history=dict(ret_code=0, ret_msg="success", data=dict(orders=[]),
                     pagination=dict(has_more=True, next_key="continuation")),
        history_pages=dict(continuation=sample("history_order_list_unfilled")), positions=dict(data=[]),
        cash=dict(cash=100000, equity=100000), state=state.to_dict())
    for name, value in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    for script, action, names in (("execute_tickets.py", ["record"], ["tickets", "responses"]),
                                   ("reconcile.py", [], ["tickets", "history", "positions", "cash", "state"])):
        args = [sys.executable, str(ROOT / "scripts" / script), *action, "--log", str(log.path)]
        for name in names:
            args.extend(["--"+name, str(tmp_path / f"{name}.json")])
        if script == "reconcile.py":
            args.extend(["--history-pages", str(tmp_path / "history_pages.json")])
        completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    assert any(event.get("orderId") == "3164623" for event in log.read())
    assert not any(event["type"] in ("fill", "halt") for event in log.read())
