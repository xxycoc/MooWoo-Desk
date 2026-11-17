"""Read-only scrubbed probe regression coverage."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from moowoo.broker import parse_cash, parse_positions, parse_history, parse_placement, snapshot_to_state
from moowoo.execution import reconcile, record
from moowoo.portfolio import PortfolioState
from test_broker_real import context, placed, sample

ROOT = Path(__file__).resolve().parents[1]


def capture(name):
    return json.loads((ROOT / "fixtures/broker" / ("real_sim_trade_" + name + ".json")).read_text())


def test_observed_cash_positions_and_margin_never_used(monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "<ORDINARY_PAPER_ACC>")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    raw = capture("cash_and_positions")
    cash = parse_cash(raw["cash_response"])
    assert cash["cash"] == 999645.21 and cash["equity"] == 1000000 and cash["reserved"] == 354.79
    assert cash["realizedProfit"] == cash["unrealizedProfit"] == 0
    assert parse_positions(raw["positions_response"]) == []
    state = snapshot_to_state([], cash, PortfolioState(cash=1000000))
    assert state.equity({}) == 1000000 and state.cash == 999645.21 and state.brokerReserved == 354.79
    raw["cash_response"]["data"]["max_power_long"] = {"poison": "must never enter sizing or risk"}
    assert parse_cash(raw["cash_response"]) == cash
    for path in (ROOT / "moowoo").glob("*.py"):
        assert "max_power_long" not in path.read_text(), path.name


def test_nested_and_top_level_pagination(context):
    payload = capture("cancel_and_history")["history_response"]
    rows = parse_history(payload)
    assert rows[0]["statusLabel"] == "cancelled (observed)"
    assert rows[1]["statusLabel"] == "accepted/resting (observed)"
    assert all(row["fillState"] == "unfilled" and not row["terminal"] for row in rows)
    moved = deepcopy(payload)
    moved["pagination"] = moved["data"].pop("pagination")
    assert parse_history(moved) == rows
    moved["data"]["pagination"] = dict(has_more=True, next_key="unexpected")
    with pytest.raises(ValueError, match="conflicting"):
        parse_history(moved)
    assert parse_placement(capture("cancel_and_history")["cancel_response"])["orderId"] == "3164637"


def test_hold_not_double_reserved_and_reconcile_repeat(context):
    ticket, log, state = placed(context)
    history = parse_history(sample("history_order_list_unfilled"))
    hold = ticket.qty * ticket.limitPrice + ticket.estFees
    cash = dict(cash=100000-hold, equity=100000, reserved=hold)
    for _ in range(2):
        state, result = reconcile({ticket.decisionId: ticket}, history, [], cash, state, log)
        assert not result["halted"]
        assert state.cash == cash["cash"] and state.brokerReserved == hold
        assert state.reservedCash == 0 and state.equity({}) == 100000
    fresh = ticket.to_dict() | dict(decisionId="2026-11-17-us:NEW", ticker="NEW")
    state.reserve(fresh)
    assert state.reservedCash == pytest.approx(hold)


def test_cancel_order_id_mismatch_does_not_release(context):
    ticket, log, state = placed(context)
    receipt = dict(decisionId=ticket.decisionId, tool="sim_trade_cancel_order",
        args=dict(acc_id="<ORDINARY_PAPER_ACC>", market=100, order_id="3164623"),
        response=capture("cancel_and_history")["cancel_response"])
    with pytest.raises(ValueError, match="order ID mismatch"):
        record({ticket.decisionId: ticket}, [receipt], log)
    assert not any(event.get("action") == "cancel" and event.get("accepted") for event in log.read())
    assert state.pendingTickets

