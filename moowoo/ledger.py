"""Durable single-writer JSONL logs and disposable SQLite projections."""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time

from .events import COMMON_FIELDS, ZERO_HASH, ValidationError, canonical_bytes, event_hash, validate_event


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    count: int
    bad_seq: int | None = None
    reason: str | None = None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_verified(path):
    events = []
    previous = ZERO_HASH
    run_id = None
    try:
        with Path(path).open("rb") as stream:
            for expected_seq, line in enumerate(stream, 1):
                try:
                    if not line.endswith(b"\n"):
                        raise ValidationError("incomplete line: missing newline")
                    event = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
                    validate_event(event)
                    if event["seq"] != expected_seq:
                        return VerifyResult(False, len(events), expected_seq, "seq gap"), events
                    if run_id is not None and event["runId"] != run_id:
                        raise ValidationError("runId changed within log")
                    if event["hash"] != event_hash(event):
                        return VerifyResult(False, len(events), expected_seq, "bad hash"), events
                    if event["prevHash"] != previous:
                        return VerifyResult(False, len(events), expected_seq, "broken prevHash link"), events
                    if line != canonical_bytes(event) + b"\n":
                        raise ValidationError("line must use canonical UTF-8 JSON followed by LF")
                except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                    return VerifyResult(False, len(events), expected_seq, f"validation error: {exc}"), events
                events.append(event)
                previous = event["hash"]
                run_id = event["runId"]
    except OSError as exc:
        return VerifyResult(False, len(events), len(events) + 1, f"validation error: {exc}"), events
    return VerifyResult(True, len(events)), events


def verify(path) -> VerifyResult:
    """Return the first failure, using its expected position as bad_seq."""
    return _read_verified(path)[0]


def _checked_events(path):
    result, events = _read_verified(path)
    if not result.ok:
        raise ValidationError(f"{path}: seq {result.bad_seq}: {result.reason}")
    return events


class EventLog:
    """Append one fsynced line at a time under an exclusive adjacent lock file.

    Existing contents are verified on open and before each append. A crash may
    leave a partial final line; it is rejected, never silently repaired.
    Use locked() across an entire state/log read-modify-write transaction.
    """

    def __init__(self, path, runId: str | None = None, *, lock_timeout=5.0):
        self.path = Path(path)
        self.lock_timeout = lock_timeout
        self._mutex = threading.RLock()
        self._depth = 0
        with self.locked():
            events = _checked_events(self.path) if self.path.exists() else []
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-us\.jsonl", self.path.name)
        inferred = None
        if match:
            date.fromisoformat(match[1])
            inferred = self.path.stem
        self.runId = runId if runId is not None else inferred
        if self.runId is None and events:
            self.runId = events[0]["runId"]
        if not isinstance(self.runId, str) or not self.runId:
            raise ValidationError("provide runId or a YYYY-MM-DD-us.jsonl filename")
        if events and events[0]["runId"] != self.runId:
            raise ValidationError("runId does not match the existing log")

    def append(self, type, payload, decisionId=None, drill=False, ts=None):
        with self.locked():
            return self._append(type, payload, decisionId, drill, ts)

    @contextmanager
    def locked(self):
        """Serialize complete transactions; stale locks fail closed."""
        with self._mutex:
            if self._depth:
                self._depth += 1
                try:
                    yield self
                finally:
                    self._depth -= 1
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock = self.path.with_name(self.path.name + ".lock")
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    break
                except FileExistsError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"event log lock timeout: {lock}; another writer or stale lock")
                    time.sleep(min(.05, max(0, deadline-time.monotonic())))
            self._depth = 1
            try:
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                yield self
            finally:
                self._depth = 0
                os.close(descriptor)
                lock.unlink()

    def read(self):
        with self.locked():
            return _checked_events(self.path) if self.path.exists() else []

    def _append(self, type, payload, decisionId=None, drill=False, ts=None):
        if not isinstance(payload, dict):
            raise ValidationError("payload must be an object")
        collisions = COMMON_FIELDS.intersection(payload)
        if collisions:
            raise ValidationError(f"payload overrides common fields: {', '.join(sorted(collisions))}")
        events = _checked_events(self.path) if self.path.exists() else []
        if events and events[0]["runId"] != self.runId:
            raise ValidationError("runId does not match the existing log")
        ticker = payload.get("ticker", payload.get("etf"))
        if decisionId is None and ticker is not None:
            decisionId = f"{self.runId}:{ticker}"
        event = dict(payload)
        event.update(
            v=0, runId=self.runId, seq=len(events) + 1,
            ts=ts if ts is not None else datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            decisionId=decisionId, type=type, drill=drill,
            prevHash=events[-1]["hash"] if events else ZERO_HASH, hash=ZERO_HASH,
        )
        validate_event(event)
        event["hash"] = event_hash(event)
        line = canonical_bytes(event) + b"\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One append write, followed by flush/fsync. No edits or truncation.
        with self.path.open("ab") as stream:
            if stream.write(line) != len(line):
                raise OSError("incomplete event write")
            stream.flush()
            os.fsync(stream.fileno())
        return event


SCHEMA = """
CREATE TABLE events (
    runId TEXT NOT NULL, seq INTEGER NOT NULL, decisionId TEXT, ts TEXT NOT NULL,
    type TEXT NOT NULL, drill INTEGER NOT NULL, hash TEXT NOT NULL,
    prevHash TEXT NOT NULL, raw TEXT NOT NULL, PRIMARY KEY (runId, seq)
);
CREATE INDEX events_decisionId ON events(decisionId);
CREATE INDEX events_seq ON events(seq);
CREATE TABLE decisions (
    runId TEXT NOT NULL, seq INTEGER NOT NULL, decisionId TEXT NOT NULL, ts TEXT NOT NULL,
    ticker TEXT NOT NULL, class TEXT NOT NULL, confidence REAL NOT NULL,
    tier TEXT NOT NULL, reason TEXT NOT NULL, newsCutoff TEXT NOT NULL,
    transcriptRef TEXT NOT NULL, credits REAL, setupScore INTEGER NOT NULL,
    creditsMissingReason TEXT,
    raw TEXT NOT NULL, PRIMARY KEY (runId, seq)
);
CREATE INDEX decisions_decisionId ON decisions(decisionId);
CREATE INDEX decisions_seq ON decisions(seq);
CREATE TABLE agent_claims (decisionId TEXT, agent TEXT, claim TEXT, ts TEXT);
CREATE INDEX agent_claims_decisionId ON agent_claims(decisionId);
CREATE TABLE outcomes (
    decisionId TEXT, horizonEnd TEXT, correct INTEGER, retVsSpy REAL,
    maxFavorable REAL, maxAdverse REAL
);
CREATE INDEX outcomes_decisionId ON outcomes(decisionId);
CREATE TABLE process_grades (
    decisionId TEXT, newsBeforeCutoff INTEGER, rulesFollowed INTEGER,
    wrongIfStated INTEGER, reasoningMatchesClass INTEGER, grade REAL
);
CREATE INDEX process_grades_decisionId ON process_grades(decisionId);
CREATE TABLE blame (decisionId TEXT, agent TEXT, cause TEXT, evidence TEXT);
CREATE INDEX blame_decisionId ON blame(decisionId);
CREATE TABLE rule_changes (
    runId TEXT NOT NULL, seq INTEGER NOT NULL, decisionId TEXT, ts TEXT NOT NULL,
    ruleId TEXT NOT NULL, before TEXT NOT NULL, after TEXT NOT NULL,
    triggerDecisionIds TEXT NOT NULL, effectiveFrom TEXT NOT NULL, raw TEXT NOT NULL,
    PRIMARY KEY (runId, seq)
);
CREATE INDEX rule_changes_decisionId ON rule_changes(decisionId);
CREATE INDEX rule_changes_seq ON rule_changes(seq);
CREATE TABLE shadow_trades (
    runId TEXT NOT NULL, seq INTEGER NOT NULL, decisionId TEXT NOT NULL, ts TEXT NOT NULL,
    book TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL,
    notional REAL NOT NULL, price REAL NOT NULL, raw TEXT NOT NULL,
    PRIMARY KEY (runId, seq)
);
CREATE INDEX shadow_trades_decisionId ON shadow_trades(decisionId);
CREATE INDEX shadow_trades_seq ON shadow_trades(seq);
"""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def build_sqlite(log_paths, db_path):
    """Verify all inputs, then atomically replace the disposable projection.

    A failed verification/build leaves an existing database untouched. No input
    log may also be the output path. Repeated (runId, seq) keys are rejected.
    """
    paths = [Path(path) for path in log_paths]
    destination = Path(db_path)
    if not paths:
        raise ValueError("at least one input log is required")
    if any(path.resolve() == destination.resolve() for path in paths):
        raise ValueError("database output must not overwrite an input log")
    all_events = []
    keys = set()
    for path in paths:
        events = _checked_events(path)
        for event in events:
            key = (event["runId"], event["seq"])
            if key in keys:
                raise ValidationError(f"duplicate event key: {key}")
            keys.add(key)
        all_events.extend(events)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    try:
        connection = sqlite3.connect(temporary)
        try:
            with connection:
                connection.executescript(SCHEMA)
                for event in all_events:
                    raw = canonical_bytes(event).decode("utf-8")
                    common = tuple(event[k] for k in ("runId", "seq", "decisionId", "ts"))
                    connection.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", common + (
                        event["type"], int(event["drill"]), event["hash"], event["prevHash"], raw))
                    kind = event["type"]
                    if kind == "rating":
                        values = tuple(event[k] for k in ("ticker", "class", "confidence", "tier", "reason", "newsCutoff", "transcriptRef", "credits", "setupScore"))
                        connection.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                           common + values + (event.get("creditsMissingReason"), raw))
                    elif kind == "rule_change":
                        connection.execute("INSERT INTO rule_changes VALUES (?,?,?,?,?,?,?,?,?,?)", common + (
                            event["ruleId"], _json(event["before"]), _json(event["after"]),
                            _json(event["triggerDecisionIds"]), event["effectiveFrom"], raw))
                    elif kind == "shadow":
                        values = tuple(event[k] for k in ("book", "ticker", "side", "notional", "price"))
                        connection.execute("INSERT INTO shadow_trades VALUES (?,?,?,?,?,?,?,?,?,?)", common + values + (raw,))
        finally:
            connection.close()
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
