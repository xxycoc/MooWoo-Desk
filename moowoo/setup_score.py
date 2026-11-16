"""Long-only daily price-action checklist with inspectable evidence.

Checklist adapted from the Trade with Stan course notes (The.Trading.Channel); ideas only.
The caller must supply bars only through its as-of date. Swings require two
completed right-hand bars; levels are recomputed at each tested session.
"""

import math

from . import config as C
from .indicators import atr, ema


def swing_indices(df, column, window=C.SWING_WINDOW):
    values = df[column]
    r = C.SWING_RADIUS
    result = []
    for i in range(max(r, len(df) - window), len(df) - r):
        neighbours = list(values.iloc[i-r:i]) + list(values.iloc[i+1:i+r+1])
        if column == "low" and all(values.iloc[i] < v for v in neighbours):
            result.append(i)
        elif column == "high" and all(values.iloc[i] > v for v in neighbours):
            result.append(i)
    return result


def support_levels(df):
    """Unfilled means no low since the up-gap has reached its pre-gap close."""
    levels = []
    for i in range(max(1, len(df) - C.GAP_WINDOW), len(df)):
        before = float(df.close.iloc[i-1])
        if df.open.iloc[i] > before and (df.low.iloc[i:] > before).all():
            levels.append(dict(kind="gap", price=before, session=str(df.index[i])))
    lows = swing_indices(df, "low")
    if lows:
        i = min(lows, key=lambda j: df.low.iloc[j])
        levels.append(dict(kind="swingLow", price=float(df.low.iloc[i]), session=str(df.index[i])))
    value = ema(df.close).iloc[-1]
    if math.isfinite(value):
        levels.append(dict(kind="ema20", price=float(value)))
    return levels


def candle_patterns(df, atr_value):
    latest = df.iloc[-1]
    body = abs(latest.close - latest.open)
    span = latest.high - latest.low
    lower = min(latest.open, latest.close) - latest.low
    upper = latest.high - max(latest.open, latest.close)
    hammer = (body > 0 and span > 0 and lower >= C.HAMMER_LOWER_BODY * body
              and upper <= C.HAMMER_UPPER_BODY * body
              and latest.close >= latest.low + C.HAMMER_CLOSE_FRACTION * span)
    engulfing = False
    if len(df) >= 2:
        previous = df.iloc[-2]
        engulfing = (previous.close < previous.open and latest.close > latest.open
                     and latest.open <= previous.close and latest.close >= previous.open)
    momentum = (span > 0 and latest.close > latest.open and body >= C.MOMENTUM_BODY_FRACTION * span
                and span >= C.MOMENTUM_ATR_RANGE * atr_value)
    return dict(hammer=bool(hammer), engulfing=bool(engulfing), momentum=bool(momentum),
                body=float(body), range=float(span), lowerWick=float(lower), upperWick=float(upper))


def setup_score(df, side="long"):
    if side != "long":
        raise ValueError("only long setups are supported")
    if df.empty or not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("provide nonempty, unique, chronological daily bars through asof")
    if not df[["open", "high", "low", "close", "volume"]].map(math.isfinite).all().all():
        raise ValueError("bars must be finite")
    points = {}
    def point(name, passed, **evidence):
        points[name] = dict(passed=bool(passed), evidence=evidence)
    averages, ranges = ema(df.close), atr(df)
    latest = df.iloc[-1]
    average, volatility = averages.iloc[-1], ranges.iloc[-1]
    number = lambda v: float(v) if math.isfinite(v) else None
    point("trend", latest.close > average, close=float(latest.close), ema20=number(average))

    touches, breaks = [], []
    for i in range(max(0, len(df)-C.LEVEL_SESSIONS), len(df)):
        history = df.iloc[:i+1]
        bar, distance = df.iloc[i], ranges.iloc[i]
        for level in support_levels(history):
            if abs(bar.low-level["price"]) <= C.LEVEL_ATR_DISTANCE * distance and bar.close > level["price"]:
                touches.append(dict(**level, testedSession=str(df.index[i]), low=float(bar.low)))
        # Resistance must exist before the breakout bar and be crossed today.
        prior = df.iloc[:i]
        highs = swing_indices(prior, "high")
        if highs:
            resistance = float(prior.high.iloc[highs].max())
            if prior.close.iloc[-1] <= resistance < bar.close:
                breaks.append(dict(price=resistance, testedSession=str(df.index[i])))
    point("level", bool(touches or breaks), supportTouches=touches, resistanceBreaks=breaks)

    highs = swing_indices(df, "high")
    line = None
    anchors = []
    if len(highs) >= 2:
        a, b = highs[-2:]
        ya, yb = float(df.high.iloc[a]), float(df.high.iloc[b])
        anchors = [dict(session=str(df.index[a]), high=ya), dict(session=str(df.index[b]), high=yb)]
        if yb < ya:
            line = yb + (yb-ya)/(b-a) * (len(df)-1-b)
    point("trendline", line is not None and latest.close > line, anchors=anchors, lineToday=line,
          close=float(latest.close))
    patterns = candle_patterns(df, volatility)
    point("candle", any(patterns[k] for k in ("hammer", "engulfing", "momentum")),
          **patterns, atr=number(volatility))
    baseline = df.volume.shift(1).rolling(C.VOLUME_PERIOD).mean().iloc[-1]
    point("volume", baseline > 0 and latest.volume >= C.VOLUME_MULTIPLIER * baseline,
          volume=float(latest.volume), prior20Mean=number(baseline))
    return dict(total=sum(p["passed"] for p in points.values()), points=points,
                asof=str(df.index[-1]), side=side)
