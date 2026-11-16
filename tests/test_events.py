import copy
import hashlib
import json

import pytest

from moowoo.events import REQUIRED_FIELDS, ValidationError, canonical_bytes, event_hash, validate_event
from moowoo.ledger import EventLog


@pytest.fixture
def samples(fixture_paths):
    events = [json.loads(line) for path in fixture_paths for line in path.read_text(encoding="utf-8").splitlines()]
    return {event["type"]: event for event in events}


@pytest.mark.parametrize("kind,field,value", [
    ("rating", "confidence", 1.5), ("rating", "confidence", -0.1),
    ("rating", "confidence", True), ("rating", "class", "maybe"),
    ("rating", "setupScore", 6), ("rating", "setupScore", 2.5),
    ("rating", "setupScore", True), ("rating", "tier", "normal"),
    ("run_started", "trdEnv", "REAL"), ("order_submitted", "trdEnv", "REAL"),
    ("fill", "source", "websocket"), ("shadow", "book", "short"),
    ("risk_verdict", "verdict", "maybe"), ("halt", "scope", "global"),
    ("order_intent", "sleeve", "other"), ("drill", "pass", 1),
    ("drill", "drill", False), ("rating", "v", True), ("rating", "seq", True),
    ("rating", "drill", 0), ("rating", "ts", "2026-11-17T14:30:00+00:00"),
    ("rating", "ts", "not-a-dateZ"), ("rating", "decisionId", "wrong:AAPL"),
    ("rating", "decisionId", None), ("rating", "credits", float("nan")),
    ("rating", "type", "unknown"), ("rating", "type", []),
])
def test_reject_invalid_values(samples, kind, field, value):
    event = copy.deepcopy(samples[kind])
    event[field] = value
    with pytest.raises(ValidationError):
        validate_event(event)


@pytest.mark.parametrize("kind", sorted(REQUIRED_FIELDS))
def test_every_required_payload_field(samples, kind):
    for field in REQUIRED_FIELDS[kind]:
        event = samples[kind].copy()
        del event[field]
        with pytest.raises(ValidationError, match="missing fields"):
            validate_event(event)


def test_nested_simulation_rule_and_allowed_extras(samples):
    event = samples["reflection_note"].copy()
    event["extension"] = {"requests": [{"trdEnv": "REAL"}]}
    with pytest.raises(ValidationError, match="SIMULATE"):
        validate_event(event)
    event["extension"]["requests"][0]["trdEnv"] = "SIMULATE"
    validate_event(event)


def test_structured_fields(samples):
    for kind, field, value in [
        ("screen", "candidates", [{}]), ("screen", "candidates", {}),
        ("daily_report", "shadowPct", {"follow": 1}),
        ("order_intent", "sizing", []), ("risk_verdict", "rules", [1]),
    ]:
        event = samples[kind].copy()
        event[field] = value
        with pytest.raises(ValidationError):
            validate_event(event)


def test_canonical_unicode_and_hash(tmp_path):
    log = EventLog(tmp_path / "2026-11-17-us.jsonl")
    event = log.append("reflection_note", {"text": "市場 café", "prompt": "Why?"})
    body = {key: value for key, value in event.items() if key != "hash"}
    expected = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert event["hash"] == hashlib.sha256(expected).hexdigest()
    assert event_hash(event) == event_hash(dict(reversed(list(event.items()))))
    assert b"\\u" not in canonical_bytes(event)


def test_invalid_append_never_changes_file(tmp_path):
    path = tmp_path / "2026-11-17-us.jsonl"
    log = EventLog(path)
    event = log.append("reflection_note", {"prompt": "Why?", "text": "Because."})
    original = path.read_bytes()
    for payload in ({"prompt": "Why?"}, {"prompt": "Why?", "text": "X", "seq": 99},
                    {"prompt": "Why?", "text": "X", "trdEnv": "REAL"}):
        with pytest.raises(ValidationError):
            log.append("reflection_note", payload)
        assert path.read_bytes() == original
    assert event["seq"] == 1
