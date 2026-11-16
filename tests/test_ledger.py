from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from moowoo.events import ZERO_HASH, ValidationError, canonical_bytes, event_hash
from moowoo.ledger import EventLog, build_sqlite, verify


ROOT = Path(__file__).resolve().parents[1]


def make_log(tmp_path):
    path = tmp_path / "2026-11-17-us.jsonl"
    log = EventLog(path)
    for number in range(3):
        log.append("reflection_note", {"prompt": "Why?", "text": f"Reason {number}"}, ts="2026-11-17T14:30:00Z")
    return path


def test_append_verify_and_reopen(tmp_path):
    path = make_log(tmp_path)
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert events[0]["prevHash"] == ZERO_HASH
    assert events[1]["prevHash"] == events[0]["hash"]
    assert events[2]["prevHash"] == events[1]["hash"]
    event = EventLog(path).append("reflection_note", {"prompt": "Next?", "text": "Continue"})
    assert event["seq"] == 4
    assert event["prevHash"] == events[2]["hash"]
    assert event["ts"].endswith("Z")
    assert verify(path).ok and verify(path).count == 4


@pytest.mark.parametrize("mutation,seq,reason", [
    ("edit", 2, "bad hash"), ("delete", 2, "seq gap"),
    ("reorder", 1, "seq gap"), ("link", 2, "broken prevHash link"),
    ("partial", 3, "validation error"), ("invalid_json", 2, "validation error"),
    ("blank", 2, "validation error"), ("duplicate_key", 2, "validation error"),
    ("run", 2, "validation error"),
    ("whitespace", 2, "validation error"),
])
def test_first_corruption_is_reported(tmp_path, mutation, seq, reason):
    path = make_log(tmp_path)
    lines = path.read_bytes().splitlines(keepends=True)
    if mutation == "edit":
        lines[1] = lines[1].replace(b"Reason 1", b"Reason 9")
    elif mutation == "delete":
        del lines[1]
    elif mutation == "reorder":
        lines[0], lines[1] = lines[1], lines[0]
    elif mutation in ("link", "run"):
        event = json.loads(lines[1])
        event["prevHash" if mutation == "link" else "runId"] = ZERO_HASH if mutation == "link" else "other"
        event["hash"] = event_hash(event)
        lines[1] = canonical_bytes(event) + b"\n"
    elif mutation == "partial":
        lines[-1] = lines[-1][:-1]
    elif mutation == "invalid_json":
        lines[1] = b"{bad json}\n"
    elif mutation == "blank":
        lines[1] = b"\n"
    elif mutation == "whitespace":
        lines[1] = b" " + lines[1]
    else:
        lines[1] = lines[1].replace(b'{', b'{"seq":2,', 1)
    path.write_bytes(b"".join(lines))
    result = verify(path)
    assert not result.ok
    assert result.bad_seq == seq
    assert result.count == seq - 1
    assert result.reason.startswith(reason)
    with pytest.raises(ValidationError):
        EventLog(path)


def test_revalidate_before_append(tmp_path):
    path = make_log(tmp_path)
    opened = EventLog(path)
    path.write_bytes(path.read_bytes().replace(b"Reason 0", b"Reason X"))
    damaged = path.read_bytes()
    with pytest.raises(ValidationError):
        opened.append("reflection_note", {"prompt": "Next?", "text": "Continue"})
    assert path.read_bytes() == damaged


def test_run_id_resolution_and_empty_log(tmp_path):
    path = tmp_path / "custom.jsonl"
    with pytest.raises(ValidationError):
        EventLog(path)
    log = EventLog(path, runId="2026-11-17-us")
    event = log.append("halt", {"reason": "Paused", "scope": "ticker", "ticker": "AAPL"})
    assert event["decisionId"] == "2026-11-17-us:AAPL"
    assert EventLog(path).runId == "2026-11-17-us"
    with pytest.raises(ValidationError):
        EventLog(path, runId="wrong")
    empty = tmp_path / "empty.jsonl"
    empty.touch()
    assert verify(empty).ok and verify(empty).count == 0
    assert not verify(tmp_path / "absent.jsonl").ok


def test_sqlite_projection_and_rebuild(fixture_paths, tmp_path):
    db = tmp_path / "ledger.sqlite"
    events = [json.loads(line) for path in fixture_paths for line in path.read_bytes().splitlines()]
    for _ in range(2):
        build_sqlite(fixture_paths, db)
        with closing(sqlite3.connect(db)) as conn:
            for table, kind in (("events", None), ("decisions", "rating"), ("rule_changes", "rule_change"), ("shadow_trades", "shadow")):
                expected = events if kind is None else [e for e in events if e["type"] == kind]
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == len(expected)
                rows = [json.loads(row[0]) for row in conn.execute(f"SELECT raw FROM {table} ORDER BY runId, seq")]
                assert rows == expected
                indexes = [row[1] for row in conn.execute(f"PRAGMA index_list({table})")]
                assert f"{table}_decisionId" in indexes and f"{table}_seq" in indexes
            for table in ("agent_claims", "outcomes", "process_grades", "blame"):
                assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            row = conn.execute("SELECT before, after, triggerDecisionIds FROM rule_changes").fetchone()
            assert json.loads(row[0])["maxPairCorrelation"] == 0.85
            assert json.loads(row[1])["maxPairCorrelation"] == 0.80
            assert json.loads(row[2]) == ["2026-11-17-us:NVDA"]
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_build_preserves_database_and_logs(fixture_paths, tmp_path):
    db = tmp_path / "ledger.sqlite"
    build_sqlite(fixture_paths, db)
    original = db.read_bytes()
    with pytest.raises(ValidationError, match="duplicate event"):
        build_sqlite([fixture_paths[0], fixture_paths[0]], db)
    with pytest.raises(ValueError, match="overwrite"):
        build_sqlite(fixture_paths, fixture_paths[0])
    with pytest.raises(ValueError, match="at least one"):
        build_sqlite([], db)
    path = fixture_paths[-1]
    path.write_bytes(path.read_bytes().replace(b"Fictional fixture", b"Modified fixture", 1))
    with pytest.raises(ValidationError, match="bad hash"):
        build_sqlite(fixture_paths, db)
    assert db.read_bytes() == original
    missing = tmp_path / "must-not-exist.sqlite"
    with pytest.raises(ValidationError):
        build_sqlite(fixture_paths, missing)
    assert not missing.exists()


def test_cli_literal_glob_and_failure_codes(fixture_paths, tmp_path):
    pattern = str(fixture_paths[0].parent / "*.jsonl")

    def run(script, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], cwd=ROOT, capture_output=True, text=True)

    result = run("verify_ledger.py", pattern)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("OK ") == 3
    result = run("build_ledger.py", "--out", tmp_path / "cli.sqlite", pattern)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rebuilt from 3 logs" in result.stdout
    result = run("verify_ledger.py", str(tmp_path / "missing*.jsonl"))
    assert result.returncode == 1 and "no logs match" in result.stdout
    fixture_paths[0].write_bytes(b"bad\n")
    result = run("verify_ledger.py", pattern)
    assert result.returncode == 1 and "seq 1" in result.stdout
    result = run("build_ledger.py", "--out", tmp_path / "bad.sqlite", pattern)
    assert result.returncode == 1 and "FAIL" in result.stdout
