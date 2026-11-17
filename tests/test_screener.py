"""Offline strategy coverage: all bars and provider responses are synthetic."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from moowoo import data
from moowoo.indicators import atr, ema, move_z, rvol
from moowoo.ledger import EventLog, verify
from moowoo.screener import screen
from moowoo.setup_score import candle_patterns, setup_score, support_levels
from moowoo.universe import evaluate_gates, fetch_candidates


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access forbidden")
    monkeypatch.setattr(data.yf, "Ticker", blocked)


def bars(size=80):
    close = 100 + np.arange(size) * 0.1 + np.sin(np.arange(size))
    return pd.DataFrame(dict(open=close-0.2, high=close+1, low=close-1,
                             close=close, volume=np.full(size, 1_000_000.0)),
                        index=pd.bdate_range("2026-07-01", periods=size))


def flat(size=80):
    frame = bars(size)
    frame.loc[:, ["open", "high", "low", "close"]] = [100, 101, 99, 100]
    return frame


def test_atr_hand_calculation_and_ema():
    frame = pd.DataFrame(dict(high=[10, 12, 13, 15], low=[8, 9, 10, 11], close=[9, 11, 12, 14]))
    # TR = 2, 3, 3, 4; seed = 8/3; next = (16/3+4)/3 = 28/9.
    result = atr(frame, 3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == pytest.approx(8/3)
    assert result.iloc[3] == pytest.approx(28/9)
    assert ema(pd.Series([1., 2., 3., 4.]), 3).iloc[-1] == pytest.approx(3.125)


def test_gap_wins_and_rvol_excludes_today():
    frame = bars()
    frame.iloc[-1, frame.columns.get_loc("open")] = frame.close.iloc[-2] * 1.1
    frame.iloc[-1, frame.columns.get_loc("volume")] = 2_000_000
    assert move_z(frame)["kind"] == "gap"
    assert move_z(frame)["movePct"] == pytest.approx(10)
    assert rvol(frame) == 2
    assert math.isnan(move_z(flat())["z"])


def test_screen_no_lookahead_ranking_and_event(tmp_path):
    frame = bars()
    asof = frame.index[-2]
    frame.loc[asof, "open"] = frame.close.iloc[-3] * 1.03
    original = screen({"passing": ["A"]}, asof, bars={"A": frame}, earnings={}, mode="raw")
    frame.iloc[-1] = [10000, 10001, 9999, 10000, 1e12]
    assert screen({"passing": ["A"]}, asof, bars={"A": frame}, earnings={}, mode="raw") == original
    strong = frame.copy()
    strong.loc[asof, "open"] *= 1.2
    result = screen({"passing": ["A", "B"]}, asof, bars={"A": strong, "B": frame},
                    earnings={"B": [str(asof.date())], "A": [str(frame.index[-1].date())]}, mode="raw")
    assert result["picked"] == ["B", "A"]
    assert result["candidates"][0]["earnings"]
    log = tmp_path / "screen.jsonl"
    EventLog(log, runId="test").append("screen", result)
    assert verify(log).ok


GOOD = dict(quoteType="EQUITY", exchange="NMS", isAdr=False, marketCap=5e9,
            floatShares=50e6, sharesOutstanding=100e6)
PRICES = dict(avgDollarVolume=50e6, lastClose=5)


@pytest.mark.parametrize("field,bad,gate", [
    ("quoteType", "ETF", "quoteType"), ("exchange", "LSE", "exchange"),
    ("isAdr", True, "adr"), ("marketCap", 5e9-1, "marketCap"),
    ("floatShares", 50e6-1, "floatShares"),
    ("sharesOutstanding", 100e6+1, "floatRatio"),
    ("avgDollarVolume", 50e6-1, "avgDollarVolume"), ("lastClose", 4.99, "lastClose"),
])
def test_gates_boundaries_and_missing(field, bad, gate):
    assert evaluate_gates(GOOD, PRICES)["passed"]
    for value in (bad, None):
        fundamentals, prices = GOOD.copy(), PRICES.copy()
        (prices if field in prices else fundamentals)[field] = value
        result = evaluate_gates(fundamentals, prices)
        if field == "isAdr" and value is None:
            assert result["passed"]  # Explicit "if detectable" exception.
        else:
            assert result["firstFailedGate"] == gate


@pytest.mark.parametrize("pattern,latest,miss", [
    ("hammer", [100, 101.1, 97.9, 101], [100, 101.1, 98.1, 101]),
    ("engulfing", [99, 102, 98, 101], [99.1, 102, 98, 101]),
    ("momentum", [100, 104, 100, 103], [100, 104, 100, 102.79]),
])
def test_candle_patterns_and_near_misses(pattern, latest, miss):
    frame = flat()
    if pattern == "engulfing":
        frame.iloc[-2, :4] = [101, 102, 98, 99]
    frame.iloc[-1, :4] = latest
    assert candle_patterns(frame, 2)[pattern]
    assert setup_score(frame)["points"]["candle"]["passed"]
    frame.iloc[-1, :4] = miss
    assert not candle_patterns(frame, 2)[pattern]
    assert not setup_score(frame)["points"]["candle"]["passed"]


def test_trend_and_volume_near_misses():
    frame = flat()
    frame.iloc[-1, frame.columns.get_loc("close")] = 100.1
    frame.iloc[-1, frame.columns.get_loc("volume")] = 1_500_000
    result = setup_score(frame)
    assert result["points"]["trend"]["passed"]
    assert result["points"]["volume"]["passed"]
    frame.iloc[-1, frame.columns.get_loc("close")] = 99.9
    frame.iloc[-1, frame.columns.get_loc("volume")] = 1_499_999
    result = setup_score(frame)
    assert not result["points"]["trend"]["passed"]
    assert not result["points"]["volume"]["passed"]
    assert result["total"] == sum(p["passed"] for p in result["points"].values())
    json.dumps(result, allow_nan=False)


def test_gap_support_and_near_miss():
    frame = flat()
    frame.iloc[-3:, :4] = [103, 104, 102, 103]
    levels = support_levels(frame)
    assert any(p["kind"] == "gap" and p["price"] == 100 for p in levels)
    result = setup_score(frame)
    assert any(p["kind"] == "gap" for p in result["points"]["level"]["evidence"]["supportTouches"])
    frame.iloc[-3:, :4] = [110, 111, 109, 110]
    assert not setup_score(frame)["points"]["level"]["passed"]
    frame.iloc[-1, frame.columns.get_loc("low")] = 100
    assert not any(p["kind"] == "gap" for p in support_levels(frame))


def test_descending_trendline_and_near_miss():
    frame = flat()
    frame.iloc[-12, frame.columns.get_loc("high")] = 110
    frame.iloc[-6, frame.columns.get_loc("high")] = 107
    # Extrapolated through positions 68 and 74 to 79: 104.5.
    frame.iloc[-1, :4] = [103, 106, 102, 104.6]
    assert setup_score(frame)["points"]["trendline"]["passed"]
    frame.iloc[-1, frame.columns.get_loc("close")] = 104.5
    assert not setup_score(frame)["points"]["trendline"]["passed"]


def test_resistance_break_and_confirmed_swings():
    frame = flat()
    frame.iloc[-6, frame.columns.get_loc("high")] = 110
    frame.iloc[-1, :4] = [109, 112, 108, 111]
    result = setup_score(frame)
    assert result["points"]["level"]["evidence"]["resistanceBreaks"]
    frame.iloc[-1, frame.columns.get_loc("close")] = 110
    assert not setup_score(frame)["points"]["level"]["evidence"]["resistanceBreaks"]


def test_data_retry_cache_and_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE", tmp_path)
    calls = []
    frame = bars(5)
    frame.columns = frame.columns.str.title()
    class Provider:
        def history(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise OSError("synthetic transient error")
            return frame.copy()
    monkeypatch.setattr(data.yf, "Ticker", lambda ticker: Provider())
    result = data.get_daily_bars(["A"], "2026-07-01", "2026-07-07")["A"]
    assert len(calls) == 2 and len(result) == 5
    assert result.attrs["source"] == "yfinance"
    assert not calls[-1]["auto_adjust"]
    pd.testing.assert_frame_equal(data.get_daily_bars(["A"], "2026-07-01", "2026-07-07")["A"],
                                  result, check_freq=False)
    assert len(calls) == 2


def test_unavailable_data_and_fundamentals(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "CACHE", tmp_path)
    calls = []
    class Provider:
        def history(self, **kwargs):
            calls.append(1)
            raise OSError("synthetic offline")
        def get_info(self):
            return {"quoteType": "EQUITY"}
        def get_earnings_dates(self, **kwargs):
            return None
    monkeypatch.setattr(data.yf, "Ticker", lambda ticker: Provider())
    frame = data.get_daily_bars(["X"], "2026-01-01", "2026-01-02")["X"]
    assert frame.empty and len(calls) == 2 and frame.attrs["unavailable"]
    fundamentals = data.get_fundamentals("X")
    assert fundamentals["marketCap"] is None and fundamentals["source"] == "yfinance"
    dates = data.get_earnings_dates("X")
    assert dates == [] and dates.source == "yfinance"


def test_top15_stale_prices_and_hash():
    frame = bars()
    frame.iloc[-1, frame.columns.get_loc("open")] *= 1.1
    tickers = [f"T{i:02}" for i in range(20)]
    result = screen({"passing": tickers}, frame.index[-1],
                    bars={t: frame for t in tickers}, earnings={}, mode="raw")
    assert result["picked"] == tickers[:5]  # PICKS-01
    stale = screen({"passing": ["A"]}, frame.index[-1], bars={"A": frame.iloc[:-1]}, earnings={})
    assert stale["skipped"]["A"] == "no bar on asof session"
    with pytest.raises(ValueError, match="hash"):
        screen({"passing": tickers, "passingSha256": "bad"}, frame.index[-1], bars={}, earnings={})


def test_seed_only_refreshes_after_all_tables_succeed(monkeypatch, tmp_path):
    path = tmp_path / "seed.txt"
    def tables(url, **kwargs):
        column = "Ticker" if "NASDAQ" in url else "Symbol"
        return [pd.DataFrame({column: ["BRK.B"] * 100})]
    monkeypatch.setattr(pd, "read_html", tables)
    tickers, source = fetch_candidates(path)
    assert tickers == ["BRK-B"] and not source["fallback"]
    def unavailable(*args, **kwargs):
        raise OSError("synthetic unavailable")
    monkeypatch.setattr(pd, "read_html", unavailable)
    tickers, source = fetch_candidates(path)
    assert tickers == ["BRK-B"] and source["fallback"]
