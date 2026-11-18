"""Signal-ATR exits with stop-before-target and next-bar trailing updates."""

import math

from . import config as C
from .desk_data import daily_frame, limit_price
from .portfolio import positive


def propose_exits(state, bars, quotes, session, run_id):
    proposals, updates, skipped = [], {}, []
    for ticker, position in sorted(state.positions.items()):
        try:
            reason = "kill liquidation" if state.tier == "kill" else None
            stop = float(position.get("stop", 0))
            armed = bool(position.get("trailArmed", False))
            highest = float(position.get("highestClose", position.get("entryPrice", position["avgCost"])))
            checked = position.get("lastExitCheck")
            if reason is None and position["kind"] != "core":
                frame = daily_frame(bars[ticker])
                entry_date = position["entryDate"]
                entry = positive(position["entryPrice"], "entryPrice")
                signal_atr = positive(position["signalAtr"], "signalAtr")
                if not math.isfinite(stop):
                    raise ValueError("invalid stop")
                target = positive(position["preDropClose"], "preDropClose") if position["kind"] == "bounce" else None
                held = frame.loc[(frame.index >= entry_date) & (frame.index <= session)]
                for day, bar in held.iterrows():
                    day_text = str(day.date())
                    if checked and day_text <= checked:
                        continue
                    # The entry-day open/high/low may precede the fill; only its close is observed after it.
                    low, high = ((bar.close, bar.close) if day_text == entry_date
                                 else (min(bar.open, bar.low), max(bar.open, bar.high)))
                    if low <= stop:
                        reason = "stop hit"
                    elif target is not None and high >= target:
                        reason = "bounce target"
                    checked = day_text
                    if reason:
                        break
                    if position["kind"] == "drift":
                        highest = max(highest, float(bar.close))
                        armed = armed or bar.close >= entry + C.TRAIL_ARM_ATR * signal_atr
                        if armed:
                            stop = max(stop, highest - C.TRAIL_ATR * signal_atr)
                quote_price = positive(quotes[ticker]["last"], "last")
                if reason is None:
                    if quote_price <= stop:
                        reason = "trailing stop" if armed else "stop hit"
                    elif target is not None and quote_price >= target:
                        reason = "bounce target"
                horizon = C.DRIFT_MAX_SESSIONS if position["kind"] == "drift" else C.BOUNCE_MAX_SESSIONS
                if reason is None and len(held) >= horizon and session != C.FINAL_DAY:
                    reason = "time exit"
                updates[ticker] = dict(stop=stop, trailArmed=bool(armed), highestClose=highest,
                                       lastExitCheck=checked)
            if reason:
                reserved = sum(ticket["qty"] for ticket in state.pendingTickets
                               if ticket["side"] == "SELL" and ticket["ticker"] == ticker)
                qty = math.floor(position["qty"] - reserved)
                if qty < 1:
                    continue
                proposals.append(dict(ticker=ticker, decisionId=f"{run_id}:{ticker}", side="SELL",
                                      qty=qty, limitPrice=limit_price(quotes[ticker], "SELL"),
                                      sleeve=position["sleeve"], kind=position["kind"], stop=stop,
                                      signalAtr=position.get("signalAtr"),
                                      preDropClose=position.get("preDropClose"), reason=reason,
                                      sizing={}, entryDecisionId=position.get("decisionId")))
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            skipped.append(dict(ticker=ticker, reason=f"exit data unavailable: {exc}"))
    return dict(proposals=proposals, updates=updates, skipped=skipped)
