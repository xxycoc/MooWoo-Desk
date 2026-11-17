"""Real offline ingestion and planner CLIs with synthetic child transcripts."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from moowoo.events import ValidationError, validate_event
from moowoo.ledger import EventLog, build_sqlite, verify
from moowoo.portfolio import PortfolioState
from moowoo.rating_schema import FIELDS, log_rating, rating_to_event
from moowoo.setup_score import setup_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plan_session import atomic_json, load_bars, read_json

RUN = "2026-11-18-us"
ASOF = "2026-11-17"
CUTOFF = "2026-11-17T21:00:00Z"
NOW = "2026-11-18T15:00:00Z"


def rating(ticker, tier="debate"):
    return dict(decisionId=f"{RUN}:{ticker}", ticker=ticker,
        **{"class": "explained_up"}, confidence=.8, tier=tier,
        reason="Synthetic earnings evidence.", evidence=[], newsCutoff=CUTOFF,
        expectedMove=dict(direction="up", horizon=5), wrongIf="Catalyst reverses.",
        model="synthetic-test", promptVersion="synthetic-version")


def reply(inputs, ticker, role):
    return inputs / "replies" / f"{RUN}:{ticker}.{role}.json"


@pytest.fixture
def inputs(tmp_path):
    path = tmp_path / "runtime" / "inputs" / RUN
    (path / "replies").mkdir(parents=True)
    atomic_json(path / "session.json", dict(runId=RUN, kind="morning", barsAsOf=ASOF))
    candidates, bars = [], {}
    dates = pd.bdate_range(end=ASOF, periods=65)
    for rank in range(1, 16):
        ticker = f"T{rank}"
        obj = rating(ticker, "debate" if rank <= 5 else "quick")
        candidates.append(dict(ticker=ticker, decisionId=obj["decisionId"], rank=rank,
            newsCutoff=CUTOFF, barsAsOf=ASOF, promptVersion=obj["promptVersion"],
            primaryAgent="manager" if rank <= 5 else "quick",
            quickSecondOpinionRequired=rank <= 5, setupScore=-1))
        bars[ticker] = [dict(date=day.date().isoformat(), open=100, high=102,
                            low=99, close=101, volume=10000) for day in dates]
        # Write verbatim text, not atomic_json: Windows treats ':' paths as NTFS
        # streams. Production Linux stores ordinary files with these exact names.
        reply(path, ticker, "analyst").write_text(json.dumps(dict(
            decisionId=obj["decisionId"], ticker=ticker, newsCutoff=CUTOFF, items=[])), encoding="utf-8")
        reply(path, ticker, "quick").write_text(json.dumps(rating(ticker, "quick")), encoding="utf-8")
        if rank <= 5:
            reply(path, ticker, "manager").write_text(json.dumps(obj), encoding="utf-8")
            for role in ("bull", "bear"):
                reply(path, ticker, role).write_text(json.dumps(dict(decisionId=obj["decisionId"],
                    stance=role, argument="Synthetic argument.", itemIds=[])), encoding="utf-8")
    atomic_json(path / "candidates.json", candidates)
    atomic_json(path / "bars.json", bars)
    return path


def cli(script, *args):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def events(inputs):
    return EventLog(inputs.parent.parent / "logs" / f"{RUN}.jsonl", runId=RUN)


def test_full_batch_replay_projection_and_real_planner(inputs):
    assert cli("ingest_ratings.py", "--inputs", inputs) == dict(accepted=15, skipped=0)
    log = events(inputs)
    rows = log.read()
    assert len(rows) == 20 and verify(log.path).ok
    assert sum(row["secondOpinion"] for row in rows) == 5
    exported = read_json(inputs / "ratings.json")
    bars, _ = load_bars(inputs / "bars.json", ASOF)
    for index, obj in enumerate(exported, 1):
        assert FIELDS <= obj.keys()
        assert obj["ticker"] == f"T{index}"
        assert obj["tier"] == ("debate" if index <= 5 else "quick")
        assert obj["setupScore"] == setup_score(bars[obj["ticker"]])["total"]
        assert "secondOpinion" not in obj and "credits" not in obj
    assert all(row["credits"] is None and row["creditsMissingReason"].strip() for row in rows)
    before = log.path.read_bytes()
    output = (inputs / "ratings.json").read_bytes()
    assert cli("ingest_ratings.py", "--inputs", inputs)["accepted"] == 15
    assert log.path.read_bytes() == before and (inputs / "ratings.json").read_bytes() == output
    database = inputs.parent.parent / "projection.sqlite"
    build_sqlite([log.path], database)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM decisions WHERE credits IS NULL AND creditsMissingReason IS NOT NULL").fetchone()[0] == 20
    state = inputs.parent.parent / "state.json"
    atomic_json(state, PortfolioState(cash=100000).to_dict())
    atomic_json(inputs / "quotes.json", dict(now=NOW, sessionDate="2026-11-18",
        quotes={obj["ticker"]: dict(last=101, bid=100.99, ask=101.01, ts=NOW) for obj in exported}))
    result = cli("plan_session.py", "--ratings", inputs / "ratings.json", "--state", state,
        "--bars", inputs / "bars.json", "--bars-asof", ASOF, "--quotes", inputs / "quotes.json",
        "--log", log.path, "--run-id", RUN, "--tickets-dir", inputs.parent.parent / "tickets")
    assert Path(result["tickets"]).is_file() and verify(log.path).ok
    assert len([row for row in log.read() if row["type"] == "reflection_note" and row.get("source") == "entry"]) == 15
    after_plan = log.path.read_bytes()
    cli("ingest_ratings.py", "--inputs", inputs)
    assert log.path.read_bytes() == after_plan


@pytest.mark.parametrize("ticker,role,accepted", [("T2", "manager", 14), ("T8", "quick", 14),
    ("T3", "bull", 14), ("T4", "analyst", 14), ("T1", "quick", 15)])
def test_missing_replies_are_terminal_skips(inputs, ticker, role, accepted):
    reply(inputs, ticker, role).unlink()
    assert cli("ingest_ratings.py", "--inputs", inputs)["accepted"] == accepted
    log = events(inputs)
    skipped = [row for row in log.read() if row["type"] == "halt"]
    assert skipped and all(row["disposition"] == "skip" for row in skipped)
    before = log.path.read_bytes()
    cli("ingest_ratings.py", "--inputs", inputs)
    assert before == log.path.read_bytes()


@pytest.mark.parametrize("damage", ["malformed", "identity", "lookahead", "version"])
def test_bad_quick_never_invalidates_manager(inputs, damage):
    obj = rating("T1", "quick")
    if damage == "identity":
        obj["decisionId"] = "other:T1"
    elif damage == "lookahead":
        obj["newsCutoff"] = "2026-11-18T21:00:00Z"
    elif damage == "version":
        obj["promptVersion"] = "wrong"
    reply(inputs, "T1", "quick").write_text("not JSON" if damage == "malformed" else json.dumps(obj))
    assert cli("ingest_ratings.py", "--inputs", inputs)["accepted"] == 15
    rows = [row for row in events(inputs).read() if row["ticker"] == "T1"]
    assert rows[0]["type"] == "rating" and rows[0]["class"] == "explained_up"
    assert rows[1]["type"] == "halt" and rows[1]["secondOpinion"]


@pytest.mark.parametrize("field,value", [("rank", "bad"), ("newsCutoff", "bad"),
    ("primaryAgent", "quick"), ("decisionId", "other:T1")])
def test_bad_candidate_is_local_skip(inputs, field, value):
    candidates = read_json(inputs / "candidates.json")
    candidates[0][field] = value
    atomic_json(inputs / "candidates.json", candidates)
    assert cli("ingest_ratings.py", "--inputs", inputs) == dict(accepted=14, skipped=1)


def test_export_failure_replays_without_duplicate_events(inputs, monkeypatch):
    import ingest_ratings

    def interrupted(*args):
        raise OSError("Synthetic interrupted export")

    monkeypatch.setattr(ingest_ratings, "atomic_json", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        ingest_ratings.ingest(inputs)
    log = events(inputs)
    before = log.path.read_bytes()
    assert not (inputs / "ratings.json").exists()
    assert cli("ingest_ratings.py", "--inputs", inputs)["accepted"] == 15
    assert log.path.read_bytes() == before


def test_primary_cutoff_and_missing_bars_are_local_skips(inputs):
    obj = rating("T1")
    obj["evidence"] = [dict(id="later", headline="Later news", source="test",
                            publishedAt="2026-11-18T00:00:00Z")]
    reply(inputs, "T1", "manager").write_text(json.dumps(obj))
    bars = read_json(inputs / "bars.json")
    del bars["T7"]
    atomic_json(inputs / "bars.json", bars)
    assert cli("ingest_ratings.py", "--inputs", inputs) == dict(accepted=13, skipped=2)
    assert {row["ticker"] for row in read_json(inputs / "ratings.json")} == {
        f"T{index}" for index in range(2, 16) if index != 7}


def test_single_cli_null_credits_and_invalid_quick(tmp_path):
    primary = tmp_path / "manager.json"
    primary.write_text(json.dumps(rating("AAA")))
    quick = tmp_path / "quick.json"
    quick.write_text("not JSON")
    log = tmp_path / "ratings.jsonl"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ingest_rating.py"),
        "--input", str(primary), "--log", str(log), "--run-id", RUN, "--ticker", "AAA",
        "--cutoff", CUTOFF, "--transcript-ref", "manager.json", "--credits", "null",
        "--credits-missing-reason", "No meter", "--setup-score", "2", "--quick-output", str(quick)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = EventLog(log).read()
    assert rows[0]["credits"] is None and rows[0]["creditsMissingReason"] == "No meter"
    assert rows[1]["type"] == "halt" and rows[1]["secondOpinion"]


@pytest.mark.parametrize("credits,reason", [(None, None), (None, " "), (1.5, "No meter")])
def test_credit_metadata_rejected(credits, reason):
    with pytest.raises(ValidationError):
        rating_to_event(rating("AAA"), CUTOFF, transcriptRef="manager.json", credits=credits,
                        creditsMissingReason=reason, setupScore=2)


def test_numeric_credits_remain_numeric(tmp_path):
    log = EventLog(tmp_path / "ratings.jsonl", runId=RUN)
    row = log_rating(log, rating("AAA"), CUTOFF, decision_id=f"{RUN}:AAA", ticker="AAA",
                     transcriptRef="manager.json", credits=1.5, setupScore=2,
                     quick_output=rating("AAA", "quick"))
    assert row["credits"] == 1.5 and "creditsMissingReason" not in row
    second = log.read()[1]
    assert second["secondOpinion"] and second["credits"] is None
    assert second["creditsMissingReason"]
    database = tmp_path / "projection.sqlite"
    build_sqlite([log.path], database)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT credits FROM decisions ORDER BY seq").fetchall() == [(1.5,), (None,)]
    row["credits"] = None
    with pytest.raises(ValidationError):
        validate_event(row)
