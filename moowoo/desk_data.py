"""Pure input validation and market calculations shared by the decision desk."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
import math

import pandas as pd

from . import config as C
from .indicators import ema
from .portfolio import positive


def daily_frame(bars):
    frame = bars.copy() if isinstance(bars, pd.DataFrame) else pd.DataFrame(bars)
    if "date" in frame.columns:
        frame = frame.set_index("date")
    frame.index = pd.DatetimeIndex(frame.index)
    if frame.index.tz is not None:
        raise ValueError("daily bars require timezone-free session dates")
    if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("bars must be nonempty, unique and chronological")
    if not frame.index.equals(frame.index.normalize()):
        raise ValueError("daily bars require session dates, not intraday times")
    frame = frame[["open", "high", "low", "close", "volume"]].astype(float)
    if not frame.map(math.isfinite).all().all():
        raise ValueError("nonfinite bars")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame.volume < 0).any():
        raise ValueError("invalid bar prices or volume")
    if ((frame.low > frame[["open", "close"]].min(axis=1)) |
            (frame.high < frame[["open", "close"]].max(axis=1))).any():
        raise ValueError("invalid OHLC range")
    return frame


def returns(bars, period):
    frame = daily_frame(bars)
    values = frame.close.pct_change(fill_method=None).iloc[-period:]
    if len(values) != period or not values.map(math.isfinite).all():
        raise ValueError(f"need {period + 1} completed closes")
    return values


def volatility(bars, period):
    value = float(returns(bars, period).std(ddof=C.STD_DDOF))
    return positive(value, "daily return volatility")


def limit_price(quote, side="BUY", *, final_liquidation=False):
    key, factor = ("ask", 1.001) if side == "BUY" else ("bid", .999)
    value = quote.get(key)
    if value is None:
        value = positive(quote.get("last"), "last") * factor
    positive(value, key)
    if final_liquidation and side == "SELL":
        # A bid-priced ticket can become unmarketable during dispatch, especially at 12:55.
        reference = quote.get("bid")
        if reference is None:
            reference = quote.get("last")
        value = Decimal(str(positive(reference, "bid"))) * Decimal("0.99")
    price = float(Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_FLOOR if final_liquidation else ROUND_HALF_UP))
    return positive(price, "limitPrice")


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps require timezone")
    return parsed


def regime_filter(bars):
    frame = daily_frame(bars)
    if len(frame) < C.REGIME_SMA_PERIOD:
        raise ValueError("regime requires 100 completed sessions")
    short = float(returns(frame, C.REGIME_VOL_SHORT_PERIOD).std(ddof=C.STD_DDOF))
    long = float(returns(frame, C.REGIME_VOL_LONG_PERIOD).std(ddof=C.STD_DDOF))
    return bool(frame.close.iloc[-1] < ema(frame.close, C.REGIME_EMA_PERIOD).iloc[-1]
                or frame.close.iloc[-1] < frame.close.iloc[-C.REGIME_SMA_PERIOD:].mean()
                or short >= C.REGIME_VOL_MULTIPLIER * long)
