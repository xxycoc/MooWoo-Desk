"""Synthetic price paths and CLI checks for preregistration section 4."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo.events import ValidationError, validate_event
from moowoo.fees import realized_pnl
from moowoo.hypotheses import book_excess, cluster_intervals, score, verdict, wilson
from moowoo.ledger import EventLog, verify
from moowoo.outcomes import experiment_sessions, grade_calls, grade_rating, read_events

ROOT = Path(__file__).resolve().parents[1]


def call(log, klass="explained_up", ticker="AAA", stamp="2026-11-17T13:30:00Z", drill=False, **extra):
    return log.append("rating", dict(ticker=ticker, **{"class": klass}, confidence=.7, tier="debate",
                      reason="Synthetic", newsCutoff="2026-11-16T21:00:00Z", transcriptRef="stub",
                      credits=0, setupScore=0, **extra), ts=stamp, drill=drill)


def bars(close=110):
    return {ticker: [dict(date=session["date"], open=100, close=close if ticker == "AAA" else 100)
                     for session in experiment_sessions()] for ticker in ("AAA", "SPY")}


def graded(tmp_path, klass="explained_up", close=110):
    log = EventLog(tmp_path / "2026-11-17-us.jsonl")
    rating = call(log, klass)
    out = EventLog(tmp_path / "outcomes.jsonl", runId="outcomes")
    outcome = grade_calls([rating], bars(close), "2026-11-27", out)[0]
    return log, rating, out, outcome


@pytest.mark.parametrize("klass,horizon,forecast,right", [
    ("explained_up", 5, "up", True), ("explained_down", 5, "down", False),
    ("unexplained_up", 3, "down", False), ("unexplained_down", 3, "up", True)])
def test_all_forecasts_including_nontraded(tmp_path, klass, horizon, forecast, right):
    log, rating, out, outcome = graded(tmp_path, klass)
    assert not any(event["type"].startswith("order") for event in log.read())
    assert outcome["horizonSessions"] == horizon
    assert outcome["entryTs"] == "2026-11-17T14:30:00Z"
    assert outcome["exitTs"] == ("2026-11-23T21:00:00Z" if horizon == 5 else "2026-11-19T21:00:00Z")
    assert outcome["forecastDirection"] == forecast and outcome["right"] is right
    assert outcome["excess"] == pytest.approx(.1)
    assert outcome["ratingHash"] == rating["hash"] and outcome["sourceRunId"] == rating["runId"]
    assert outcome["decisionId"] == rating["decisionId"]
    assert verify(out.path).ok


@pytest.mark.parametrize("stamp,entry,exit_date,truncated", [
    ("2026-11-17T14:30:00Z", "2026-11-18", "2026-11-24", False),
    ("2026-11-20T21:00:00Z", "2026-11-23", "2026-11-27", True),
    ("2026-11-26T12:00:00Z", "2026-11-27", "2026-11-27", True)])
def test_next_open_holiday_and_final_early_close(tmp_path, stamp, entry, exit_date, truncated):
    log = EventLog(tmp_path / "source.jsonl", runId="source")
    rating = call(log, stamp=stamp)
    result = grade_rating(rating, bars(), "2026-11-27")
    assert result["entryTs"] == entry + "T14:30:00Z"
    assert result["exitTs"] == exit_date + ("T18:00:00Z" if exit_date.endswith("27") else "T21:00:00Z")
    assert result["truncated"] is truncated
    assert grade_rating(rating, bars(), "2026-11-19") is None


def test_no_entry_and_zero_wrong(tmp_path):
    log = EventLog(tmp_path / "source.jsonl", runId="source")
    rating = call(log, stamp="2026-11-27T14:30:00Z")
    result = grade_rating(rating, bars(), "2026-11-27")
    assert not result["graded"] and "no next" in result["reason"]
    rating = call(log, ticker="OTHER")
    rating["ticker"] = "AAA"
    assert grade_rating(rating, bars(100), "2026-11-27")["right"] is False
    benchmark = bars(110)
    for row in benchmark["SPY"]:
        row["close"] = 120
    assert grade_rating(rating, benchmark, "2026-11-27")["right"] is False


@pytest.mark.parametrize("fault", ["stock", "spy", "duplicate", "invalid", "malformed"])
def test_missing_prices_never_disappear(tmp_path, fault):
    log = EventLog(tmp_path / "source.jsonl", runId="source")
    rating = call(log)
    prices = bars()
    if fault == "stock": del prices["AAA"]
    elif fault == "spy": del prices["SPY"]
    elif fault == "duplicate": prices["AAA"].append(prices["AAA"][0])
    elif fault == "invalid": prices["AAA"][0]["open"] = 0
    else: prices["AAA"] = [None]
    out = EventLog(tmp_path / "outcomes.jsonl", runId="outcomes")
    written = grade_calls([rating], prices, "2026-11-27", out)
    assert len(written) == 1 and written[0]["graded"] is False and written[0]["reason"]
    result = score([rating] + written)
    assert result["H1"]["count"] == 0 and len(result["missing"]) == 1
    assert result["H3"]["verdict"] == "not assessable"


def test_idempotent_missing_recovery_and_input_overlap(tmp_path):
    source = EventLog(tmp_path / "source.jsonl", runId="source")
    rating = call(source)
    out = EventLog(tmp_path / "outcomes.jsonl", runId="outcomes")
    assert len(grade_calls([rating], {}, "2026-11-27", out)) == 1
    assert grade_calls([rating], {}, "2026-11-27", out) == []
    assert len(grade_calls([rating], bars(), "2026-11-27", out)) == 1
    events = read_events([source.path, out.path, out.path])
    before = out.path.read_bytes()
    assert grade_calls(events, bars(), "2026-11-27", out) == []
    assert out.path.read_bytes() == before
    assert score(events)["H1"]["count"] == 1
    assert score([events[0], *reversed(events[1:])])["H1"]["count"] == 1


def test_second_opinion_and_drill_exclusion(tmp_path):
    log = EventLog(tmp_path / "source.jsonl", runId="source")
    primary = call(log)
    second = call(log, secondOpinion=True)
    drill = call(log, ticker="DRILL", drill=True)
    out = EventLog(tmp_path / "outcomes.jsonl", runId="outcomes")
    written = grade_calls([primary, second, drill], bars(), "2026-11-27", out)
    assert len(written) == 2
    result = score([primary, second, drill] + written)
    assert result["H1"]["count"] == 1 and result["excludedSecondOpinions"] == 1
    assert result["H3"]["brier"] == pytest.approx(.09)


def test_wilson_and_bootstrap_rules():
    assert wilson(0, 0) is None
    assert wilson(5, 10) == pytest.approx([.2365930905, .7634069095])
    assert verdict(wilson(30, 30), .5) == "supported"
    assert verdict(wilson(0, 30), .5) == "rejected"
    assert verdict([0, .1], 0) == "can't tell yet"
    rows = [dict(entrySession="a", first=1., second=2.), dict(entrySession="a", first=3., second=6.),
            dict(entrySession="b", first=5., second=10.)]
    intervals = cluster_intervals(rows, ["first", "second"])
    assert intervals == cluster_intervals(rows, ["first", "second"])
    assert intervals["first"] == [2., 5.]
    assert intervals["second"] == [4., 10.]


def book(log, outcome, name, exit_price=110, skipped=False):
    return log.append("shadow", dict(book=name, ticker="AAA", side="BUY", notional=0 if skipped else 1000,
        price=100, sleeve="satellite", completed=True, entryTs=outcome["entryTs"], exitTs=outcome["exitTs"],
        qty=0 if skipped else 10, entryPrice=100, exitPrice=exit_price, spyReturn=0.,
        exitRule="drift", skipped=skipped, reason="ineligible direction" if skipped else "horizon exit"))


def test_h2_paired_costs_cash_and_unavailable(tmp_path):
    log, rating, out, outcome = graded(tmp_path)
    llm, follow, fade = book(log, outcome, "llm"), book(log, outcome, "follow", 105), book(log, outcome, "fade", skipped=True)
    result = score(log.read() + out.read())
    assert result["H2"]["verdict"] == "supported"
    assert result["H2"]["count"] == 1
    expected = realized_pnl(10, 100, 110)["returnNet"] - realized_pnl(10, 100, 105)["returnNet"]
    assert result["H2"]["comparisons"]["versusFollow"]["mean"] == pytest.approx(expected)
    assert result["H2"]["dispositions"]
    assert score([rating, outcome, llm, follow])["H2"]["verdict"] == "can't tell yet"
    assert book_excess(fade | dict(spyReturn=.03), "fade", outcome) == -.03
    with pytest.raises(ValueError):
        book_excess(fade | dict(skipped=False, qty=10), "fade", outcome)
    with pytest.raises(ValueError):
        book_excess(llm | dict(sleeve="core"), "llm", outcome)
    negative = llm | dict(exitPrice=90)
    assert score([rating, outcome, negative, follow, fade])["H2"]["verdict"] == "rejected"


def test_outcome_validation_and_source_binding(tmp_path):
    log, rating, out, outcome = graded(tmp_path)
    for key, value in (("right", False), ("horizonSessions", 3), ("stockReturn", .5), ("entryPrice", None)):
        with pytest.raises(ValidationError):
            validate_event(outcome | {key: value})
    with pytest.raises(ValueError, match="prelogged"):
        score([rating, outcome | dict(confidence=.9)])
    with pytest.raises(ValueError, match="duplicate terminal"):
        score([rating, outcome, outcome])


def test_grade_score_cli_and_cached_bars(tmp_path):
    log = EventLog(tmp_path / "source.jsonl", runId="source")
    call(log)
    prices = {ticker: dict(bars=json.dumps(dict(data=[row | dict(date=row["date"] + "T00:00:00.000")
                                                    for row in rows]))) for ticker, rows in bars().items()}
    path = tmp_path / "bars.json"
    path.write_text(json.dumps(prices))
    out = tmp_path / "outcomes.jsonl"
    grade_command = [sys.executable, "scripts/grade_calls.py", "--logs", str(log.path), "--bars-asof", "2026-11-27",
                     "--bars", str(path), "--log", str(out)]
    for _ in range(2):
        completed = subprocess.run(grade_command, cwd=ROOT, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
    assert len(EventLog(out).read()) == 1
    destination = tmp_path / "hypotheses.json"
    completed = subprocess.run([sys.executable, "scripts/score_hypotheses.py", "--logs", str(log.path), str(out),
                                "--out", str(destination)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(destination.read_text())
    assert result["H1"]["count"] == 1 and result["H3"]["verdict"] == "met"
    assert result["H2"]["unavailable"] and result["seed"] == 20261117 and result["resamples"] == 2000
