"""Yahoo data adapters. No inferred fundamentals; failures carry provenance.

Yahoo OHLC and volume are already split-adjusted. auto_adjust=False avoids
dividend-adjusted prices, which would distort actual gaps and dollar volume.
end is inclusive here (unlike Yahoo's exclusive end).
"""

from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

from . import config as C

CACHE = Path(__file__).resolve().parents[1] / ".cache" / "prices"
COLUMNS = ["open", "high", "low", "close", "volume"]


def _provider(ticker):
    # Keep Yahoo's cookie/timezone caches inside the authorized repository too.
    yf.set_tz_cache_location(str(CACHE.parent / "yfinance"))
    return yf.Ticker(ticker)


def session_index(index):
    index = pd.DatetimeIndex(index)
    return index.tz_localize(None).normalize()


def _empty(reason):
    frame = pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([]), dtype=float)
    frame.attrs.update(source="yfinance", unavailable=reason)
    return frame


def get_daily_bars(tickers, start, end):
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start > end:
        raise ValueError("start must not exceed end")
    CACHE.mkdir(parents=True, exist_ok=True)
    output = {}
    for ticker in tickers:
        key = hashlib.sha256(f"split-only-v1:{ticker}:{start.date()}:{end.date()}".encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                frame = pd.read_json(StringIO(cached["bars"]), orient="table")
                frame.attrs.update(cached["metadata"])
                output[ticker] = frame
                continue
            except (ValueError, KeyError, OSError):
                pass  # A damaged cache is recoverable from the original source.
        for attempt in range(C.DATA_ATTEMPTS):
            try:
                frame = _provider(ticker).history(
                    start=start.strftime("%Y-%m-%d"),
                    end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    auto_adjust=False, actions=False, timeout=C.DATA_TIMEOUT_SECONDS,
                    raise_errors=True,
                )
                frame.columns = frame.columns.str.lower()
                frame = frame[COLUMNS].copy()
                frame.index = session_index(frame.index)
                frame = frame.loc[(frame.index >= start) & (frame.index <= end)].sort_index()
                frame = frame[~frame.index.duplicated(keep="last")]
                if frame.empty:
                    raise ValueError("no bars returned")
                frame.attrs.update(source="yfinance", unavailable=None,
                                   retrievedAt=datetime.now(timezone.utc).isoformat())
                # Do not cache a still-forming current session.
                if end.date() < datetime.now(timezone.utc).date():
                    path.write_text(json.dumps(dict(bars=frame.to_json(orient="table"),
                                                    metadata=frame.attrs)), encoding="utf-8")
                output[ticker] = frame
                break
            except Exception as exc:
                output[ticker] = _empty(f"{type(exc).__name__}: {exc}")
    return output


def get_fundamentals(ticker):
    result = dict.fromkeys(("marketCap", "sharesOutstanding", "floatShares", "quoteType",
                           "exchange", "isAdr"))
    result.update(source="yfinance", error=None,
                  retrievedAt=datetime.now(timezone.utc).isoformat())
    try:
        info = _provider(ticker).get_info()
        for key in result.keys() & info.keys():
            value = info[key]
            missing = pd.isna(value) or (isinstance(value, (int, float)) and not math.isfinite(value))
            result[key] = None if missing else value
        # Yahoo does not consistently expose an ADR flag. Positive name evidence
        # excludes known depositary receipts; absence is recorded as unknown.
        name = str(info.get("longName", "")) + " " + str(info.get("shortName", ""))
        if any(term in name.lower() for term in C.ADR_NAME_TERMS):
            result["isAdr"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


class EarningsDates(list):
    """List-compatible result, including provenance when empty."""
    source = "yfinance"

    def __init__(self, dates=(), error=None):
        super().__init__(dates)
        self.error = error


def get_earnings_dates(ticker):
    try:
        frame = _provider(ticker).get_earnings_dates(limit=C.EARNINGS_HISTORY_LIMIT)
        if frame is None:
            return EarningsDates(error="no earnings dates returned")
        return EarningsDates(sorted(set(session_index(frame.index).strftime("%Y-%m-%d"))))
    except Exception as exc:
        return EarningsDates(error=f"{type(exc).__name__}: {exc}")
