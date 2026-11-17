"""Competition virtual fees in USD; the sell levy is capped per order."""
from decimal import Decimal
from . import config as C
from .portfolio import positive


def estimate_fees(side, qty):
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    positive(qty, "qty", zero=True)
    if qty == 0:
        return 0.0
    levy = min(Decimal(str(C.FEE_SELL_CAP)), Decimal(str(C.FEE_PER_SHARE_SOLD))*Decimal(str(qty))) if side == "SELL" else Decimal(0)
    return float(Decimal(str(C.FEE_PER_ORDER)) + levy)


def realized_pnl(qty, entry_price, exit_price):
    """One complete buy/sell round trip, including both virtual fees."""
    positive(qty, "qty")
    positive(entry_price, "entry_price")
    positive(exit_price, "exit_price")
    cost = qty * entry_price + estimate_fees("BUY", qty)
    proceeds = qty * exit_price - estimate_fees("SELL", qty)
    return dict(pnl=proceeds-cost, returnNet=proceeds/cost-1,
                fees=estimate_fees("BUY", qty)+estimate_fees("SELL", qty))
