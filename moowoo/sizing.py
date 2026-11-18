"""Ratings select trade kind, never quantities. All sizing is deterministic."""

import math

from . import config as C
from .desk_data import daily_frame, limit_price, volatility
from .indicators import atr, ema, rvol
from .portfolio import positive
from .fees import estimate_fees
from .setup_score import support_levels


def propose_entry(rating, bars, quote, equity, tier="normal"):
    def skip(reason):
        return dict(status="skip", ticker=rating.get("ticker", "UNKNOWN"),
                    decisionId=rating.get("decisionId"), reason=reason)

    kind = {"explained_up": "drift", "unexplained_down": "bounce"}.get(rating.get("class"))
    if kind is None:
        return skip("classification does not authorize a long entry")
    try:
        positive(equity, "equity")
        confidence = positive(rating["confidence"], "confidence", zero=True)
        if confidence > 1 or rating["tier"] not in ("quick", "debate", "single"):
            raise ValueError("invalid confidence or rating tier")
        if tier not in ("normal", "reduced", "exits_only", "kill"):
            raise ValueError("invalid account tier")
        frame = daily_frame(bars)
        sigma = volatility(frame, C.MOVE_PERIOD)
        signal_atr = positive(float(atr(frame).iloc[-1]), "signal ATR")
        relative_volume = positive(rvol(frame), "RVOL", zero=True)
        close = float(frame.close.iloc[-1])
        levels = [level["price"] for level in support_levels(frame) if level["price"] <= close]
        support = max(levels) if levels else None
        eligible = close > ema(frame.close).iloc[-1] or (support is not None and close-support <= signal_atr)
        if kind == "bounce" and (not eligible or relative_volume >= C.RVOL_CAP):
            return skip("bounce requires trend-or-support and RVOL < RVOL_CAP")
        if kind == "drift" and relative_volume < C.R_drift:
            return skip("drift RVOL below R_drift")
        price = limit_price(quote)
        factor = (C.QUICK_TIER_SIZE_FACTOR if rating["tier"] == "quick" else 1)
        factor *= .5 if tier == "reduced" else 1
        notional = C.PER_NAME_CAP * equity * confidence * min(1, .02 / sigma) * factor
        qty = math.floor(notional / price)
        if qty * price < C.MIN_ENTRY_NOTIONAL:
            return skip("below_min_notional")
        stop = max(price - (C.K_drift if kind == "drift" else C.K_bounce) * signal_atr,
                   support - signal_atr if support is not None else -math.inf)
        if stop >= price:
            return skip("entry is already at or below its stop")
        target = float(frame.close.iloc[-2]) if kind == "bounce" else None
        if target is not None and price >= target:
            return skip("bounce target already reached before entry")
        return dict(status="proposal", decisionId=rating["decisionId"], ticker=rating["ticker"],
                    side="BUY", qty=qty, limitPrice=price, estFees=estimate_fees("BUY", qty), sleeve="satellite", kind=kind,
                    stop=stop, signalAtr=signal_atr, preDropClose=target,
                    reason=f"{kind} from {rating['class']}",
                    sizing=dict(confidence=confidence, dailySd=sigma, factor=factor,
                                proposedNotional=notional, rvol=relative_volume, support=support))
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return skip(f"unavailable or invalid input: {exc}")
