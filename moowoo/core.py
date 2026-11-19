"""Inverse-volatility core targets and whole-share rebalance proposals."""

import math

from . import config as C
from .desk_data import daily_frame, limit_price, volatility


def weights(bars):
    frames = {ticker: daily_frame(bars[ticker]) for ticker in C.CORE_ETFS}
    dates = frames[C.CORE_ETFS[0]].index[-C.CORE_VOLATILITY_PERIOD-1:]
    if any(not frame.index[-C.CORE_VOLATILITY_PERIOD-1:].equals(dates) for frame in frames.values()):
        raise ValueError("core volatility sessions must align")
    inverse = {ticker: 1/volatility(frame, C.CORE_VOLATILITY_PERIOD) for ticker, frame in frames.items()}
    total = sum(inverse.values())
    return {ticker: C.CORE_WEIGHT * value/total for ticker, value in inverse.items()}


def propose_core(state, bars, quotes, prices, run_id):
    targets = weights(bars)
    equity = state.equity(prices)
    if equity <= 0:
        raise ValueError("core requires positive equity")
    proposals = []
    for ticker, target in targets.items():
        actual_notional = state.exposure(prices, ticker=ticker)
        actual = actual_notional/equity
        if abs(actual-target)/target + 1e-12 < C.CORE_REBALANCE_BAND:
            continue
        side = "BUY" if actual < target else "SELL"
        price = limit_price(quotes[ticker], side)
        qty = math.floor(abs(target*equity-actual_notional)/price)
        if side == "SELL":
            reserved = sum(ticket["qty"] for ticket in state.pendingTickets
                           if ticket["side"] == "SELL" and ticket["ticker"] == ticker)
            qty = min(qty, math.floor(state.positions.get(ticker, {}).get("qty", 0)-reserved))
        if qty >= 1:
            proposals.append(dict(ticker=ticker, decisionId=f"{run_id}:{ticker}", side=side,
                                  qty=qty, limitPrice=price, sleeve="core", kind="core", stop=0,
                                  reason="core initial buy" if actual == 0 else "core rebalance band",
                                  sizing=dict(targetWeight=target, actualWeight=actual)))
    return sorted(proposals, key=lambda proposal: proposal["side"] != "SELL")


def projected_core_state(state, tickets):
    """Conditional sizing only: never persist projected cash or position changes."""
    from .portfolio import PortfolioState
    projected = PortfolioState.from_dict(state.to_dict())
    dependencies = []
    for ticket in tickets:
        if ticket["sleeve"] != "core" or ticket["side"] != "SELL":
            continue
        held = projected.positions[ticket["ticker"]]
        if ticket["qty"] > held["qty"]:
            raise ValueError("conditional core sell exceeds holding")
        held["qty"] -= ticket["qty"]
        if not held["qty"]:
            del projected.positions[ticket["ticker"]]
        projected.cash += ticket["qty"] * ticket["limitPrice"] - ticket["estFees"]
        dependencies.append(ticket["decisionId"])
    return projected, dependencies


def require_core_fills(ticket, manifest, state, logs, prices):
    """Use actual cash/core budgets; otherwise wait for reconciled sell fills."""
    if ticket.sleeve != "core" or ticket.side != "BUY":
        return
    from . import config as C
    by_id = {t["decisionId"]: t for t in manifest["tickets"]}
    # Derive dependencies as well as checking the manifest, so removing metadata cannot bypass the gate.
    expected = {t["decisionId"] for t in manifest["tickets"] if t["sleeve"] == "core" and t["side"] == "SELL"}
    dependencies = set(manifest.get("coreSellDependencies", {}).get(ticket.decisionId, []))
    if dependencies != expected:
        raise ValueError("core sell dependency manifest mismatch")
    if state.halted or state.tier in ("kill", "exits_only") or state.dailyLossHalted:
        raise ValueError("core buy blocked by current account halt/tier")
    if not any(t["decisionId"] == ticket.decisionId and t["qty"] == ticket.qty for t in state.pendingTickets):
        raise ValueError("core buy reservation missing or changed")
    equity = state.equity(prices)
    # All pending buys remain reserved. Include their fees in equity after execution.
    fees = sum(t["estFees"] for t in state.pendingTickets if t["side"] == "BUY")
    effective_equity = equity - fees
    cash_funded = (state.cash - state.reservedCash >= C.CASH_FLOOR * effective_equity - 1e-9
                   and state.exposure(prices, sleeve="core") <= C.CORE_WEIGHT * effective_equity + 1e-9)
    # Unfilled sells contribute neither cash nor room; every pending buy stays reserved.
    if not (C.CORE_REBALANCE_CASH_FUNDED and cash_funded):
        events = logs.read()
        for decision in dependencies:
            sell = by_id[decision]
            orders = [e for e in events if e["type"] == "order_submitted" and not e["drill"] and e["decisionId"] == decision]
            if len(orders) != 1:
                raise ValueError("core buy requires recorded and reconciled sell fills")
            fill = state.execution.get("fills", {}).get(orders[0]["orderId"], {})
            if fill.get("filledQty") != sell["qty"] or any(t["decisionId"] == decision for t in state.pendingTickets):
                raise ValueError("core buy requires full reconciled sell fills")
    if state.exposure(prices, sleeve="core") > C.CORE_WEIGHT * effective_equity + 1e-9:
        raise ValueError("core target exceeded on reconciled post-sell state")
    if state.cash - state.reservedCash < C.CASH_FLOOR * effective_equity - 1e-9:
        raise ValueError("cash floor exceeded on reconciled post-sell state")
    if equity <= state.sessionStartEquity * (1-C.DAILY_LOSS_HALT) + 1e-9:
        raise ValueError("core buy blocked by current daily loss")
