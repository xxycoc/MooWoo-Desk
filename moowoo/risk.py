"""Ordered, fail-closed risk checks. Exits bypass entry gates, not idempotency."""

from datetime import date
import math

from . import config as C
from .desk_data import daily_frame, instant, regime_filter, returns
from .portfolio import positive

RULES = ("kill_or_halted", "exits_only", "daily_loss", "final_day", "first_minutes",
         "regime", "duplicate_decision", "max_orders", "stale_price", "spread",
         "correlation", "bounce_count", "per_name_cap", "satellite_cap", "cash_floor", "adv")


def check(proposal, state, market):
    ticker, side, quantity = proposal["ticker"], proposal["side"], proposal["qty"]
    if side not in ("BUY", "SELL") or type(quantity) is not int or quantity < 1:
        raise ValueError("proposal requires BUY/SELL and positive whole shares")
    price = positive(proposal["limitPrice"], "limitPrice")
    if proposal["sleeve"] not in ("core", "satellite"):
        raise ValueError("invalid sleeve")
    if proposal["sleeve"] == "core" and ticker not in C.CORE_ETFS:
        raise ValueError("core exemption is only for frozen core ETFs")
    if not isinstance(proposal["decisionId"], str) or not proposal["decisionId"]:
        raise ValueError("decisionId required")
    if side == "SELL":
        held = state.positions.get(ticker, {}).get("qty", 0)
        pending = sum(ticket["qty"] for ticket in state.pendingTickets
                      if ticket["side"] == "SELL" and ticket["ticker"] == ticker
                      and ticket["decisionId"] != proposal["decisionId"])
        if quantity > held - pending:
            raise ValueError("sell exceeds unreserved long position")
    entry = side == "BUY"
    satellite = proposal["sleeve"] == "satellite"
    results, fired, veto, qty = [], None, False, quantity

    def equity():
        return positive(state.equity(market["prices"]), "equity")

    def regime():
        return regime_filter(market["bars"][C.REGIME_BENCHMARK])

    def ceiling(budget):
        return max(0, math.floor((budget + 1e-9) / price))

    def satellite_room(cap):
        return ceiling(cap * equity() - state.exposure(market["prices"], sleeve="satellite"))

    def daily_loss():
        return state.dailyLossHalted or state.equity(market["prices"]) <= state.sessionStartEquity * (1-C.DAILY_LOSS_HALT) + 1e-9

    def regime_check():
        if not regime() or not satellite:
            return None
        if proposal["kind"] == "bounce" and C.REGIME_STOP_BOUNCE:
            return "veto"
        return satellite_room(C.REGIME_SATELLITE_CAP)

    def stale():
        age = (instant(market["now"]) - instant(market["quotes"][ticker]["ts"])).total_seconds()
        return age < 0 or age > C.STALE_PRICE_SECONDS

    def spread():
        quote = market["quotes"][ticker]
        bid, ask = positive(quote["bid"], "bid"), positive(quote["ask"], "ask")
        if ask < bid:
            raise ValueError("crossed quote")
        return (ask-bid)/((ask+bid)/2) > C.MAX_SPREAD + 1e-12

    def correlated():
        if not satellite:
            return False
        others = {symbol for symbol, position in state.positions.items()
                  if position["sleeve"] == "satellite" and symbol != ticker}
        others.update(ticket["ticker"] for ticket in state.pendingTickets
                      if ticket["sleeve"] == "satellite" and ticket["side"] == "BUY"
                      and ticket["ticker"] != ticker)
        if not others:
            return False
        values = returns(market["bars"][ticker], C.CORRELATION_PERIOD)
        for other in sorted(others):
            comparison = returns(market["bars"][other], C.CORRELATION_PERIOD)
            if not values.index.equals(comparison.index):
                raise ValueError("correlation sessions do not align")
            value = float(values.corr(comparison))
            if not math.isfinite(value):
                raise ValueError("correlation unavailable")
            if value > C.MAX_CORRELATION:
                return True
        return False

    def bounce_count():
        symbols = {symbol for symbol, position in state.positions.items() if position["kind"] == "bounce"}
        symbols.update(ticket["ticker"] for ticket in state.pendingTickets
                       if ticket["kind"] == "bounce" and ticket["side"] == "BUY")
        return proposal["kind"] == "bounce" and ticker not in symbols and len(symbols) >= C.MAX_BOUNCE_POSITIONS

    def satellite_cap():
        if not satellite:
            return None
        stepped = state.stepUp.get("enabled", False) and market["sessionDate"] >= state.stepUp.get("effectiveFrom", "9999-12-31")
        cap = C.SATELLITE_CAP_STEP_UP if stepped else C.SATELLITE_CAP
        return satellite_room(min(cap, C.REGIME_SATELLITE_CAP) if regime() else cap)

    def adv_cap():
        frame = daily_frame(market["bars"][ticker]).iloc[-C.VOLUME_PERIOD:]
        if len(frame) != C.VOLUME_PERIOD:
            raise ValueError("ADV needs 20 completed sessions")
        adv = positive(float((frame.close * frame.volume).mean()), "ADV")
        return ceiling(C.MAX_ADV_FRACTION * adv)

    def final_day():
        session = date.fromisoformat(market["sessionDate"])
        return C.NO_NEW_ENTRIES_ON_FINAL_DAY and session >= date.fromisoformat(C.FINAL_DAY)

    def minutes():
        elapsed = market["minutesSinceOpen"]
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed):
            raise ValueError("minutesSinceOpen required")
        return market.get("isRegularSession", True) is False or elapsed < C.NO_ORDERS_FIRST_MINUTES

    checks = [
        ("kill_or_halted", lambda: state.halted or state.tier == "kill", "veto"),
        ("exits_only", lambda: state.tier == "exits_only", "veto"),
        ("daily_loss", daily_loss, "veto"),
        ("final_day", final_day, "veto"),
        ("first_minutes", minutes, "veto"),
        ("regime", regime_check, "mixed"),
        ("duplicate_decision", lambda: proposal["decisionId"] in state.ticketedDecisionIds, "veto"),
        ("max_orders", lambda: state.ordersPlacedThisSession + sum(
            not ticket.get("submitted", False) for ticket in state.pendingTickets
            if ticket.get("sessionDate", ticket.get("createdTs", "")[:10]) == market["sessionDate"]
        ) >= C.MAX_ORDERS_PER_SESSION, "veto"),
        ("stale_price", stale, "veto"),
        ("spread", spread, "veto"),
        ("correlation", correlated, "veto"),
        ("bounce_count", bounce_count, "veto"),
        ("per_name_cap", lambda: ceiling(C.PER_NAME_CAP * equity() - state.exposure(
            market["prices"], ticker=ticker)) if satellite else None, "resize"),
        ("satellite_cap", satellite_cap, "resize"),
        ("cash_floor", lambda: ceiling(state.cash - state.reservedCash - C.CASH_FLOOR * equity() - C.FEE_PER_ORDER), "resize"),
        ("adv", adv_cap, "resize"),
        ("satellite_invalidated", lambda: satellite and state.stepUp.get("invalidated", False), "veto"),
        ("core_target", lambda: ceiling(C.CORE_WEIGHT * equity() - state.exposure(
            market["prices"], sleeve="core")) if not satellite else None, "resize"),
    ]
    for name, evaluate, action in checks:
        if not entry and name != "duplicate_decision":
            results.append(dict(rule=name, result="not_applicable"))
            continue
        try:
            value = evaluate()
            failed = (bool(value) if action == "veto" else value == "veto" or
                      (value is not None and value < qty))
            detail = dict(rule=name, result="pass")
            if failed:
                fired = fired or name
                if action == "veto" or value == "veto":
                    veto = True
                    detail["result"] = "veto"
                else:
                    qty = min(qty, value)
                    detail.update(result="resize", qtyAfter=qty)
                    if qty < 1 or qty * price < C.MIN_ENTRY_NOTIONAL:
                        veto = True
                        detail["result"] = "veto"
            results.append(detail)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            fired, veto = fired or name, True
            results.append(dict(rule=name, result="unavailable", reason=str(exc)))
    if entry and qty * price < C.MIN_ENTRY_NOTIONAL:
        fired, veto = fired or "below_min_notional", True
        results.append(dict(rule="below_min_notional", result="veto"))
    verdict = "veto" if veto else "resize" if qty != quantity else "approve"
    return dict(ticker=ticker, verdict=verdict, rules=[item["rule"] for item in results],
                firedRule=fired, qtyAfter=0 if veto else qty, checks=results)
