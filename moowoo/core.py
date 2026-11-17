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
