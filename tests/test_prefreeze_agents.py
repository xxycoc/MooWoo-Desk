"""Offline staged evaluation and rating boundary checks."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from hash_prompts import prompt_version
from qca_deploy import build_payloads
from qca_evals import prepare, collect, argument
from run_evals import evaluate
from moowoo.events import ValidationError
from moowoo.ledger import EventLog
from moowoo.rating_schema import parse_rating, rating_to_event, validate_rating

ROOT = Path(__file__).resolve().parents[1]


def rating(case, role):
    brief = case["brief"]
    klass = case["expected"]["class"]
    direction = klass.rsplit("_", 1)[1]
    if klass.startswith("unexplained"):
        direction = "down" if direction == "up" else "up"
    return dict(decisionId=brief["decisionId"], ticker=brief["ticker"],
                **{"class": klass}, confidence=.7, tier="quick" if role == "quick" else "debate",
                reason="Synthetic evaluation stub.", evidence=[], newsCutoff=brief["newsCutoff"],
                expectedMove=dict(direction=direction, horizon=5 if klass.startswith("explained") else 3),
                wrongIf="Wrong signed excess return.", model="efficient" if role == "quick" else "ultimate",
                promptVersion=prompt_version())


def outputs(case):
    return {role: json.dumps(dict(decisionId=case["brief"]["decisionId"], stance=role,
                                 argument="Synthetic argument.", itemIds=[])) if role in ("bull", "bear")
            else json.dumps(rating(case, role)) for role in ("bull", "bear", "manager", "quick")}


@pytest.fixture
def case():
    return json.loads((ROOT / "evals/earnings_beat.json").read_text())


def test_cloud_setup_installs_and_checks_once():
    payloads = build_payloads()
    setup = next(op["body"]["config"]["setup_script"] for op in payloads["operations"] if op["key"] == "environment")
    assert "python3 -m pip install -e '.[dev]'" in setup
    assert "--no-deps" not in setup
    assert setup.count("python3 -m pytest -q") == 1
    assert "exit 1" in setup and "set -euo pipefail" in setup
    assert "git checkout --detach" in setup and "REPO_REVISION" in setup
    assert setup.index("pip install") < setup.index("pytest")


def test_staged_chain_and_independence(case):
    initial = prepare(case)
    assert [request["agent"] for request in initial] == ["bull", "bear", "quick"]
    transcripts = outputs(case)
    ready = prepare(case, transcripts)
    for request in initial:
        assert request == next(item for item in ready if item["agent"] == request["agent"])
    manager = json.loads(next(item for item in ready if item["agent"] == "manager")["messages"][1]["content"])
    assert manager["brief"] == case["brief"]
    assert manager["bull"] == json.loads(transcripts["bull"])
    assert manager["bear"] == json.loads(transcripts["bear"])
    assert "quick" not in manager
    assert collect(case, transcripts)["requests"] == ready
    with pytest.raises(ValueError):
        collect(case, {"manager": transcripts["manager"]})
    transcripts["bear"] = transcripts["bull"]
    with pytest.raises(ValidationError):
        prepare(case, transcripts)



def test_argument_cutoff_compares_instants(case):
    case["brief"]["newsCutoff"] = "2026-11-17T14:00:00Z"
    case["brief"]["items"] = [{"id": "before", "publishedAt": "2026-11-17T15:00:00+02:00"},
                                {"id": "after", "publishedAt": "2026-11-17T13:30:00-01:00"}]
    output = dict(decisionId=case["brief"]["decisionId"], stance="bull",
                  argument="Synthetic argument.", itemIds=["before"])
    assert argument(case, "bull", json.dumps(output))["itemIds"] == ["before"]
    output["itemIds"] = ["after"]
    with pytest.raises(ValidationError):
        argument(case, "bull", json.dumps(output))

def test_full_chain_cli_with_stubs(tmp_path):
    raw = tmp_path / "raw"
    for path in (ROOT / "evals").glob("*.json"):
        case = json.loads(path.read_text())
        directory = raw / case["id"]
        directory.mkdir(parents=True)
        for role, text in outputs(case).items():
            (directory / (role + ".txt")).write_text(text)
    prepared, collected = tmp_path / "prepared", tmp_path / "collected"
    for action, destination in (("prepare", prepared), ("collect", collected)):
        process = subprocess.run([sys.executable, "scripts/qca_evals.py", action,
                                  "--outputs", str(raw), "--out", str(destination)],
                                 cwd=ROOT, capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
    report = tmp_path / "report.json"
    process = subprocess.run([sys.executable, "scripts/run_evals.py", "--outputs", str(collected),
                              "--report", str(report)], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr + process.stdout
    assert json.loads(report.read_text())["passed"] == 4
    target = next(collected.glob("*.json"))
    data = json.loads(target.read_text())
    data["requests"][0]["messages"][1]["content"] = "tampered"
    target.write_text(json.dumps(data))
    assert evaluate(collected)["passed"] == 3


def test_fence_and_reason(case, caplog):
    obj = rating(case, "quick")
    fenced = "\x60\x60\x60json\n" + json.dumps(obj) + "\n\x60\x60\x60"
    assert parse_rating(fenced) == obj
    assert "Stripped single JSON code fence" in caplog.text
    obj["reason"] = "a" * 600
    validate_rating(obj, obj["newsCutoff"])
    obj["reason"] += "a"
    with pytest.raises(ValidationError, match="600"):
        validate_rating(obj, obj["newsCutoff"])


@pytest.mark.parametrize("text", ["hello {}", '{} {}', '{"a":1,"a":2}', '{"a":NaN}',
                                 '\x60\x60\x60json\n{}\n\x60\x60\x60\nextra',
                                 '\x60\x60\x60python\n{}\n\x60\x60\x60',
                                 '\x60\x60\x60json\n{}\n\x60\x60\x60\n\x60\x60\x60json\n{}\n\x60\x60\x60', None])
def test_malformed_json_stays_rejected(text):
    with pytest.raises(ValidationError):
        parse_rating(text)


def test_debate_ingestion_cli(case, tmp_path):
    transcripts = outputs(case)
    bull = json.loads(transcripts["bull"])
    bull["argument"] = "word " * 140
    transcripts["bull"] = json.dumps(bull)
    for role, text in transcripts.items():
        (tmp_path / (role + ".json")).write_text(text)
    log_path = tmp_path / "ratings.jsonl"
    brief = case["brief"]
    process = subprocess.run([sys.executable, "scripts/ingest_rating.py", "--input", str(tmp_path / "manager.json"),
        "--log", str(log_path), "--run-id", brief["decisionId"].rsplit(":", 1)[0],
        "--ticker", brief["ticker"], "--cutoff", brief["newsCutoff"], "--transcript-ref", "stub-transcripts",
        "--credits", "0", "--setup-score", "0", "--bull-output", str(tmp_path / "bull.json"),
        "--bear-output", str(tmp_path / "bear.json"), "--quick-output", str(tmp_path / "quick.json")],
        cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    event = EventLog(log_path).read()[0]
    assert len(event["bullSummary"]) == 600
    assert event["bearSummary"] == "Synthetic argument."
    assert event["quickSecondOpinion"] == {"class": case["expected"]["class"], "confidence": .7}
    assert event["class"] == case["expected"]["class"]
    quick = rating(case, "quick")
    quick["decisionId"] = "other:" + brief["ticker"]
    with pytest.raises(ValidationError, match="identity"):
        rating_to_event(rating(case, "manager"), brief["newsCutoff"], transcriptRef="stub", credits=0,
                        setupScore=0, quick_output=quick)


@pytest.mark.parametrize("role", ["bull", "bear"])
def test_argument_exact_keys_and_cutoff_boundary(case, role):
    case["brief"]["items"] = [
        {"id": "at", "publishedAt": case["brief"]["newsCutoff"]},
        {"id": "later", "publishedAt": "2099-01-01T00:00:00Z"},
    ]
    valid = dict(decisionId=case["brief"]["decisionId"], stance=role,
                 argument="Only eligible evidence supports this argument.", itemIds=["at"])
    assert argument(case, role, json.dumps(valid)) == valid
    for field in ("ticker", "newsCutoff", "model", "promptVersion"):
        with pytest.raises(ValidationError, match=f"invalid {role} argument"):
            argument(case, role, json.dumps({**valid, field: "extra provenance"}))
    with pytest.raises(ValidationError, match=f"invalid {role} citations"):
        argument(case, role, json.dumps({**valid, "itemIds": ["later"]}))
    empty = {**valid, "argument": "No eligible evidence supports the thesis.", "itemIds": []}
    assert argument(case, role, json.dumps(empty)) == empty
