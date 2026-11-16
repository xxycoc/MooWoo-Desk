"""Candidate discovery and fail-closed stock/ETF gates."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .data import get_daily_bars, get_fundamentals, session_index
from .events import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
INDEX_PAGES = {
    "sp500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol"),
    "sp400": ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "Symbol"),
    "nasdaq100": ("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies", "Ticker"),
}


def fetch_candidates(seed_path=ROOT / "config" / "seed_tickers.txt"):
    tickers = set()
    try:
        for url, column in INDEX_PAGES.values():
            tables = pd.read_html(url, storage_options={"User-Agent": "MooWooDesk/0.1"})
            table = next(t for t in tables if column in t.columns and len(t) >= 90)
            tickers.update(str(t).strip().replace(".", "-") for t in table[column])
        seed_path = Path(seed_path)
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_path.write_text("# Wikipedia constituents fetched " + datetime.now(timezone.utc).isoformat()
                             + "\n" + "\n".join(sorted(tickers)) + "\n", encoding="utf-8")
        return sorted(tickers), {"source": "Wikipedia", "pages": INDEX_PAGES, "fallback": False}
    except Exception as exc:
        if not Path(seed_path).exists():
            raise RuntimeError(f"Wikipedia fetch failed and no seed exists: {exc}") from exc
        tickers = [s.strip() for s in Path(seed_path).read_text(encoding="utf-8").splitlines()
                   if s.strip() and not s.startswith("#")]
        return sorted(set(tickers)), {"source": "seed_tickers.txt", "fallback": True, "error": str(exc)}


def finite(value):
    return isinstance(value, (int, float, np.number)) and not isinstance(value, bool) and np.isfinite(value)


def price_values(df):
    if df.empty:
        return dict(avgDollarVolume=None, lastClose=None, lastSession=None)
    window = df.tail(C.VOLUME_PERIOD)
    valid = (len(window) == C.VOLUME_PERIOD
             and np.isfinite(window[["close", "volume"]]).all().all()
             and (window.close > 0).all() and (window.volume >= 0).all())
    average = float((window.close * window.volume).mean()) if valid else None
    close = float(df.close.iloc[-1]) if finite(df.close.iloc[-1]) else None
    return dict(avgDollarVolume=average, lastClose=close, lastSession=str(df.index[-1].date()))


def evaluate_gates(fundamentals, prices):
    values = {k: fundamentals.get(k) for k in
              ("quoteType", "exchange", "isAdr", "marketCap", "floatShares", "sharesOutstanding")}
    values.update(prices)
    shares, floating = values["sharesOutstanding"], values["floatShares"]
    values["floatRatio"] = (float(floating / shares) if finite(shares) and shares > 0
                            and finite(floating) else None)
    checks = {}
    def check(name, passed, reason):
        checks[name] = dict(passed=bool(passed), reason=None if passed else reason)
    check("quoteType", values["quoteType"] == C.STOCK_QUOTE_TYPE, "missing or not EQUITY")
    check("exchange", values["exchange"] in C.US_EXCHANGES, "missing or not a supported US exchange")
    check("adr", values["isAdr"] is not True, "detected depositary receipt")
    for name, threshold in C.GATES.items():
        value = values.get(name)
        check(name, finite(value) and value >= threshold,
              "missing" if not finite(value) else f"below {threshold}")
    failed = next((name for name, result in checks.items() if not result["passed"]), None)
    return dict(passed=failed is None, firstFailedGate=failed, values=values, gates=checks)


def build_universe(asof, tickers, candidate_source, progress=print):
    date = pd.Timestamp(asof).normalize()
    # The freeze uses completed sessions strictly before the freeze date; this
    # avoids ingesting a partial US session when run from Singapore on Nov 16.
    end = date - pd.Timedelta(days=1)
    start = date - pd.Timedelta(days=C.HISTORY_CALENDAR_DAYS)
    records = {}
    for i, ticker in enumerate(tickers, 1):
        bars = get_daily_bars([ticker], start, end)[ticker]
        assert bars.empty or session_index(bars.index).max() < date
        fundamental = get_fundamentals(ticker)
        result = evaluate_gates(fundamental, price_values(bars))
        result["data"] = dict(source="yfinance", bars=bars.attrs, fundamentals=fundamental)
        records[ticker] = result
        if i % 25 == 0:
            progress(f"Processed {i}/{len(tickers)}; passing {sum(r['passed'] for r in records.values())}", flush=True)
    core = {}
    for ticker, bars in get_daily_bars(C.CORE_ETFS, start, end).items():
        values = price_values(bars)
        value = values["avgDollarVolume"]
        core[ticker] = dict(**values, passed=finite(value) and value >= C.GATES["avgDollarVolume"],
                            source="yfinance", data=bars.attrs)
    passing = sorted(t for t, r in records.items() if r["passed"])
    failures = Counter(r["firstFailedGate"] for r in records.values() if not r["passed"])
    return dict(date=str(date.date()), priceCutoff=str(end.date()),
                retrievedAt=datetime.now(timezone.utc).isoformat(),
                thresholds=dict(**C.GATES, quoteType=C.STOCK_QUOTE_TYPE, exchanges=C.US_EXCHANGES,
                                excludeDetectedADR=True, volumeSessions=C.VOLUME_PERIOD),
                tickers=records, passing=passing, coreEtfs=core,
                counts=dict(candidates=len(tickers), passing=len(passing), failed=len(tickers)-len(passing),
                            firstGateFailures=dict(failures.most_common())),
                source=dict(prices="yfinance", fundamentals="yfinance", candidates=candidate_source),
                passingSha256=hashlib.sha256(canonical_bytes(passing)).hexdigest())
