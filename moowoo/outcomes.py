"""Offline preregistered forecast grading, separate from trade P&L."""

from datetime import date, datetime
import json
import math

from . import config as C
from .events import ValidationError


def experiment_sessions():
    """Regular US sessions in this frozen experiment; Thanksgiving is closed."""
    return [dict(date=f"2026-11-{day:02d}", open=f"2026-11-{day:02d}T14:30:00Z",
                 close=f"2026-11-{day:02d}T{'18' if day == 27 else '21'}:00:00Z")
            for day in (17, 18, 19, 20, 23, 24, 25, 27)]


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def price(bars, ticker, session, field):
    values = bars.get(ticker)
    if isinstance(values, dict) and "bars" in values:
        try:
            values = json.loads(values["bars"])["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid cached bars: {ticker}") from exc
    if not isinstance(values, list):
        raise ValueError(f"missing bars: {ticker}")
    if any(not isinstance(row, dict) for row in values):
        raise ValueError(f"invalid bar rows: {ticker}")
    rows = [row for row in values if str(row.get("date", ""))[:10] == session]
    if len(rows) != 1:
        raise ValueError(f"missing or duplicate {ticker} bar: {session}")
    value = rows[0].get(field)
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"invalid {ticker} {field}: {session}")
    return value


def grade_rating(rating, bars, asof):
    date.fromisoformat(asof)
    explained = rating["class"].startswith("explained_")
    direction = rating["class"].rsplit("_", 1)[1]
    forecast = direction if explained else ("down" if direction == "up" else "up")
    horizon = 5 if explained else 3
    result = dict(ticker=rating["ticker"], sourceRunId=rating["runId"], ratingHash=rating["hash"],
                  ratingTs=rating["ts"], newsCutoff=rating["newsCutoff"],
                  confidence=rating["confidence"], horizonSessions=horizon, forecastDirection=forecast,
                  secondOpinion=rating.get("secondOpinion", False), tier=rating["tier"],
                  entryTs=None, entryPrice=None, exitTs=None, exitPrice=None, stockReturn=None,
                  spyReturn=None, excess=None, right=False, graded=False, barsAsOf=asof)
    result["class"] = rating["class"]
    if instant(rating["ts"]) < instant("2026-11-17T00:00:00Z"):
        return result | dict(reason="rating precedes experiment decision window")
    sessions = [session for session in experiment_sessions()
                if instant(session["open"]) > instant(rating["ts"]) and session["date"] <= C.FINAL_DAY]
    if not sessions:
        if asof < C.FINAL_DAY:
            return None
        return result | dict(reason="no next regular-session open before final valuation")
    window = sessions[:horizon]
    entry, exit_session = window[0], window[-1]
    if exit_session["date"] > asof:
        return None
    result.update(entryTs=entry["open"], exitTs=exit_session["close"],
                  observedSessions=len(window), truncated=len(window) < horizon)
    if instant(rating["newsCutoff"]) > instant(rating["ts"]):
        return result | dict(reason="rating predates its news cutoff")
    try:
        entry_price = price(bars, rating["ticker"], entry["date"], "open")
        exit_price = price(bars, rating["ticker"], exit_session["date"], "close")
        spy_entry = price(bars, "SPY", entry["date"], "open")
        spy_exit = price(bars, "SPY", exit_session["date"], "close")
    except ValueError as exc:
        return result | dict(reason=str(exc))
    stock_return, spy_return = exit_price / entry_price - 1, spy_exit / spy_entry - 1
    excess = stock_return - spy_return
    return result | dict(entryPrice=entry_price, exitPrice=exit_price, stockReturn=stock_return,
                         spyReturn=spy_return, excess=excess,
                         right=excess > 0 if forecast == "up" else excess < 0, graded=True)


def read_events(paths):
    from .ledger import EventLog
    events, seen = [], {}
    for path in paths:
        for event in EventLog(path).read():
            key = (event["runId"], event["seq"])
            if key in seen and seen[key] != event["hash"]:
                raise ValidationError("conflicting copies of ledger event")
            if key not in seen:
                events.append(event)
                seen[key] = event["hash"]
    return events


def grade_calls(events, bars, asof, log):
    written = []
    with log.locked():
        previous = {}
        seen = set()
        for event in events + log.read():
            if event["hash"] in seen:
                continue
            seen.add(event["hash"])
            if event["type"] == "outcome" and not event["drill"]:
                key = event["ratingHash"]
                if previous.get(key, {}).get("graded"):
                    if event["graded"]:
                        raise ValidationError("duplicate terminal outcome")
                else:
                    previous[key] = event
        for rating in events:
            if rating["type"] != "rating" or rating["drill"]:
                continue
            prior = previous.get(rating["hash"])
            if prior and prior["graded"]:
                continue
            outcome = grade_rating(rating, bars, asof)
            if outcome is None or (prior and not outcome["graded"] and prior.get("reason") == outcome.get("reason")):
                continue
            event = log.append("outcome", outcome, decisionId=rating["decisionId"])
            previous[rating["hash"]] = event
            written.append(event)
    return written
