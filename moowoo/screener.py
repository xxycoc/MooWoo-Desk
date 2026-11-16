"""Deterministic, date-bounded daily mover screening."""

import hashlib
import math

import pandas as pd

from . import config as C
from .data import get_daily_bars, get_earnings_dates, session_index
from .events import canonical_bytes
from .indicators import abnormal_move_z, move_z, rvol


def through_asof(df, asof):
    frame = df.copy()
    frame.index = session_index(frame.index)
    frame = frame.loc[frame.index <= pd.Timestamp(asof).normalize()].sort_index()
    if frame.index.has_duplicates:
        raise ValueError("duplicate daily sessions")
    assert frame.empty or frame.index.max() <= pd.Timestamp(asof).normalize(), "lookahead"
    return frame


def screen(universe, asof, *, bars=None, earnings=None, mode=None):
    """Inject bars and earnings mappings for offline use. Future rows are removed.

    Requires the latest bar to equal asof; no stale bar is treated as today's move.
    A newer frozen universe is permitted for the requested diagnostic replay and
    disclosed in metadata; it is not a point-in-time universe backtest.
    """
    tickers = universe["passing"]
    mode = C.MOVE_MODE if mode is None else mode
    if mode not in ("raw", "abnormal"):
        raise ValueError("MOVE_MODE must be raw or abnormal")
    if "passingSha256" in universe:
        digest = hashlib.sha256(canonical_bytes(tickers)).hexdigest()
        if digest != universe["passingSha256"]:
            raise ValueError("universe passing-list hash mismatch")
    date = pd.Timestamp(asof).normalize()
    if bars is None:
        bars = get_daily_bars(list(dict.fromkeys(tickers + (["SPY"] if mode == "abnormal" else []))),
                              date - pd.Timedelta(days=C.HISTORY_CALENDAR_DAYS), date)
    spy = through_asof(bars.get("SPY", pd.DataFrame()), date)
    candidates, skipped, earnings_errors = [], {}, {}
    for ticker in tickers:
        if ticker not in bars:
            skipped[ticker] = "bars unavailable"
            continue
        df = through_asof(bars[ticker], date)
        if df.empty or df.index[-1] != date:
            skipped[ticker] = "no bar on asof session"
            continue
        move = abnormal_move_z(df, spy) if mode == "abnormal" else move_z(df)
        relative_volume = rvol(df)
        if not math.isfinite(move["z"]) or not math.isfinite(relative_volume):
            skipped[ticker] = "insufficient valid history or zero denominator"
            continue
        if abs(move["z"]) < C.MOVE_MIN_Z:
            continue
        dates = get_earnings_dates(ticker) if earnings is None else earnings.get(ticker, [])
        if getattr(dates, "error", None):
            earnings_errors[ticker] = dates.error
        sessions = set(df.index[-C.EARNINGS_SESSIONS:])
        is_earnings = any(pd.Timestamp(d).tz_localize(None).normalize() in sessions for d in dates)
        candidates.append(dict(ticker=ticker, movePct=move["movePct"], z=move["z"],
                               moveKind=move["kind"], rvol=relative_volume, earnings=is_earnings))
    candidates.sort(key=lambda row: (not row["earnings"],
                                     -abs(row["z"]) * min(row["rvol"], C.RVOL_CAP), row["ticker"]))
    return dict(candidates=candidates, picked=[r["ticker"] for r in candidates[:C.PICK_COUNT]],
                asof=str(date.date()), universeDate=universe.get("date"),
                source="yfinance", moveMode=mode, skipped=skipped, earningsErrors=earnings_errors)


def format_table(result):
    lines = ["Ticker   Move%       z    RVOL Earnings Picked Kind",
             "------- -------- ------- ------- -------- ------ -----"]
    for r in result["candidates"]:
        lines.append(f"{r['ticker']:<7} {r['movePct']:>8.2f} {r['z']:>7.2f} {r['rvol']:>7.2f} "
                     f"{str(r['earnings']):<8} {str(r['ticker'] in result['picked']):<6} {r['moveKind']}")
    if not result["candidates"]:
        lines.append("(no qualifying movers)")
    return "\n".join(lines)
