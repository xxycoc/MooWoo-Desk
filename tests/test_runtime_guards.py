"""Runtime regressions with real logs and mocked remote ownership only."""

from argparse import Namespace
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo import calendar, config, runlock
from moowoo.execution import preflight, prepare
from moowoo.ledger import EventLog
from moowoo.persistence import LedgerError, LedgerStore
from moowoo.portfolio import PortfolioState
from moowoo.runtime_logs import existing_log, index_logs
from moowoo.tickets import OrderTicket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dispatch_check
import reconcile as reconcile_cli
import run_session
from _execution import frozen_config
from hash_prompts import prompt_version
from plan_session import atomic_json
from test_execution import fixture

NOW = datetime.fromisoformat("2026-11-17T15:00:00+00:00")
RUN = "2026-11-17-us"
LIVE_NAME = "2026-11-17-morning-8e73d892dd8f-screen.jsonl"


def note(path, run_id):
    log = EventLog(path, runId=run_id)
    log.append("reflection_note", dict(prompt="test", text="preserved"))
    return log


def test_live_shaped_log_identity_and_handoff(tmp_path):
    log = note(tmp_path / "logs" / LIVE_NAME, "2026-11-16-us")
    before = log.path.read_bytes()
    opened = existing_log(log.path)
    assert opened.runId == "2026-11-16-us"
    events = opened.read()
    atomic_json(tmp_path / "handoffs/test.json", dict(logs={f"logs/{LIVE_NAME}":
        dict(count=len(events), hash=events[-1]["hash"])}))
    LedgerStore(tmp_path).verify_logs()
    current = note(tmp_path / "logs/current.jsonl", "current")
    logs = reconcile_cli.RuntimeLogs([opened, current], current)
    logs.append("reflection_note", dict(prompt="test", text="routed"), decisionId="2026-11-16-us:AAPL")
    assert log.path.read_bytes().startswith(before)
    assert log.read()[-1]["text"] == "routed"


def test_event_identity_overrides_date_filename(tmp_path):
    log = note(tmp_path / "2026-11-17-us.jsonl", "2026-11-16-us")
    assert existing_log(log.path).runId == "2026-11-16-us"


def test_duplicate_identities_rejected(tmp_path):
    first = note(tmp_path / "logs" / LIVE_NAME, "2026-11-16-us")
    second = note(tmp_path / "logs/other.jsonl", first.runId)
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        index_logs([first, second])
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        reconcile_cli.RuntimeLogs([first], second)
    with pytest.raises(LedgerError, match="ambiguous duplicate"):
        LedgerStore(tmp_path).verify_logs()


def test_finish_preserves_live_shaped_log(tmp_path, monkeypatch):
    source = note(tmp_path / "logs" / LIVE_NAME, "2026-11-16-us")
    before = source.path.read_bytes()
    note(tmp_path / "logs/current.jsonl", "current")
    atomic_json(tmp_path / ".session.json", dict(kind="morning", runId="current", holder="owner", phase="reconcile"))
    monkeypatch.setattr(run_session, "require_owned", lambda *args: None)
    monkeypatch.setattr(LedgerStore, "save", lambda *args, **kwargs: dict(saved=True))
    result = run_session.run(Namespace(kind="morning", phase="finish", dir=tmp_path,
                                      remote=run_session.REMOTE), NOW)
    assert result["saved"]
    LedgerStore(tmp_path).verify_logs()
    assert source.path.read_bytes() == before
    assert f"logs/{LIVE_NAME}" in json.loads((tmp_path / "handoffs/current.json").read_text())["logs"]


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    frozen = frozen_config()
    ticket = OrderTicket(decisionId=RUN + ":AAA", ticker="AAA", side="BUY", qty=50,
        limitPrice=100., sleeve="satellite", kind="drift", stop=94., reason="synthetic",
        configHash=frozen["configHash"], createdTs=calendar.utc_stamp(NOW), estFees=.99, signalAtr=2.)
    log = EventLog(tmp_path / f"logs/{RUN}.jsonl", runId=RUN)
    prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-17\npromptVersion={prompt_version()}\n"
    preflight(fixture("accounts"), PortfolioState(cash=100000), frozen, prereg, prompt_version(), ["AAA"], log)
    result = prepare({ticket.decisionId: ticket}, log)
    atomic_json(tmp_path / f"receipts/{RUN}/prepare-test.json", result)
    atomic_json(tmp_path / f"tickets/{RUN}.json", dict(runId=RUN, configHash=frozen["configHash"], tickets=[ticket.to_dict()]))
    atomic_json(tmp_path / ".session.json", dict(kind="morning", runId=RUN, holder="owner", phase="prepare"))
    lock = dict(holder="owner", kind="morning", startedAt=NOW.isoformat(), expiresAt=(NOW + timedelta(minutes=45)).isoformat())
    monkeypatch.setattr(LedgerStore, "fetch", lambda self: True)
    monkeypatch.setattr(LedgerStore, "remote_lock", lambda self: lock)
    args = Namespace(kind="morning", decision_id=ticket.decisionId, dir=tmp_path)
    return args, ticket, log, result["orders"][0], lock


def test_dispatch_exact_prepared_args_and_no_writes(prepared):
    args, ticket, log, order, lock = prepared
    before = log.path.read_bytes()
    assert dispatch_check.run(args, NOW) == dict(ok=True, decisionId=ticket.decisionId, args=order["args"])
    assert log.path.read_bytes() == before
    assert config.STALE_PRICE_SECONDS == 60


def test_dispatch_only_selected_ticket_freshness(prepared):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"tickets/{RUN}.json"
    manifest = json.loads(path.read_text())
    manifest["tickets"].append(ticket.to_dict() | dict(decisionId=RUN + ":BBB", createdTs="2026-11-16T15:00:00Z"))
    atomic_json(path, manifest)
    assert dispatch_check.run(args, NOW + timedelta(seconds=60))["ok"]
    with pytest.raises(ValueError, match="expired"):
        dispatch_check.run(args, NOW + timedelta(seconds=61))
    with pytest.raises(ValueError, match="expired"):
        dispatch_check.run(args, NOW - timedelta(seconds=1))


@pytest.mark.parametrize("mutation,reason", [
    ("owner", "ownership"), ("expired", "expired"), ("phase", "prepared session"),
    ("kind", "prepared session"), ("missing", "missing or duplicated"),
    ("duplicate", "missing or duplicated"), ("args", "tool arguments"),
    ("receipt", "tool arguments"), ("failed", "resolved"), ("halt", "halted"),
])
def test_dispatch_refusals(prepared, mutation, reason):
    args, ticket, log, order, lock = prepared
    if mutation == "owner":
        lock["holder"] = "other"
    elif mutation == "expired":
        lock["expiresAt"] = NOW.isoformat()
    elif mutation == "kind":
        args.kind = "watch"
    elif mutation == "phase":
        path = args.dir / ".session.json"
        atomic_json(path, json.loads(path.read_text()) | dict(phase="plan"))
    elif mutation == "missing":
        args.decision_id = RUN + ":BBB"
    elif mutation == "duplicate":
        path = args.dir / f"tickets/{RUN}.json"
        manifest = json.loads(path.read_text())
        manifest["tickets"].append(ticket.to_dict())
        atomic_json(path, manifest)
    elif mutation in ("args", "receipt"):
        receipt = dict(orders=[order])
        if mutation == "args":
            order["args"]["qty"] = "1"
        else:
            receipt["orders"] = []
        atomic_json(args.dir / f"receipts/{RUN}/prepare-test.json", receipt)
    elif mutation == "failed":
        log.append("reflection_note", dict(prompt="Execution", text="failed", executionAction="placement_failed", attempt=1), decisionId=ticket.decisionId)
    elif mutation == "halt":
        log.append("halt", dict(reason="test", scope="run"))
    with pytest.raises((ValueError, LedgerError), match=reason):
        dispatch_check.run(args, NOW)


def test_dispatch_clock_after_ownership_fetch(prepared, monkeypatch):
    args, ticket, log, order, lock = prepared
    current = NOW
    class Clock:
        @staticmethod
        def now(zone):
            return current
    monkeypatch.setattr(dispatch_check, "datetime", Clock)
    def delayed_check(*arguments):
        nonlocal current
        current = NOW + timedelta(seconds=61)
    monkeypatch.setattr(dispatch_check, "require_owned", delayed_check)
    with pytest.raises(ValueError, match="expired"):
        dispatch_check.run(args)


@pytest.mark.parametrize("moment,reason", [
    ("2026-11-17T21:00:00Z", "market closed"),
    ("2026-11-17T14:32:00Z", "first five"),
    ("2026-11-27T15:00:00Z", "final day"),
])
def test_dispatch_calendar_gates(prepared, monkeypatch, moment, reason):
    args, ticket, log, order, lock = prepared
    monkeypatch.setattr(dispatch_check, "require_owned", lambda *args: None)
    path = args.dir / f"tickets/{RUN}.json"
    manifest = json.loads(path.read_text())
    fresh = OrderTicket(**(ticket.to_dict() | dict(createdTs=moment, ticketHash="")))
    manifest["tickets"] = [fresh.to_dict()]
    atomic_json(path, manifest)
    log.append("reflection_note", dict(prompt="Execution", text="prepared", executionAction="prepared", attempt=1,
                                       ticketHash=fresh.ticketHash), decisionId=ticket.decisionId)
    with pytest.raises(ValueError, match=reason):
        dispatch_check.run(args, moment)


def test_dispatch_cli_json(prepared, monkeypatch, capsys):
    args, ticket, log, order, lock = prepared
    class Clock:
        @staticmethod
        def now(zone):
            return NOW
    monkeypatch.setattr(dispatch_check, "datetime", Clock)
    monkeypatch.setattr(runlock, "datetime", Clock)
    monkeypatch.setattr(sys, "argv", ["dispatch_check.py", "--kind", "morning", "--decision-id", ticket.decisionId,
                                    "--dir", str(args.dir)])
    assert dispatch_check.main() == 0
    assert json.loads(capsys.readouterr().out)["args"] == order["args"]
    lock["holder"] = "other"
    assert dispatch_check.main() == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_dispatch_real_cli_missing_context(tmp_path):
    result = subprocess.run([sys.executable, "scripts/dispatch_check.py", "--kind", "watch", "--decision-id", "missing",
                             "--dir", str(tmp_path)], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert json.loads(result.stdout) == dict(ok=False, reason="invalid or missing runtime data")


class LeaseStore:
    def __init__(self, root):
        self.directory = root
        self.lock = dict(holder="owner", kind="morning", startedAt=NOW.isoformat(),
                         expiresAt=(NOW + timedelta(minutes=45)).isoformat())
        atomic_json(root / "locks/run.lock", self.lock)
        self.saves = []
        self.before_save = lambda: None

    def fetch(self):
        return True

    def remote_lock(self):
        return deepcopy(self.lock)

    def save(self, message, holder, *, release, before_push):
        self.before_save()
        before_push()
        self.saves.append((holder, release))
        self.lock = json.loads((self.directory / "locks/run.lock").read_text())


def test_renewal_and_hard_cap(tmp_path):
    store = LeaseStore(tmp_path)
    first = runlock.renew(store, "owner", NOW + timedelta(minutes=40))
    assert calendar.local_time(first["expiresAt"]) == NOW + timedelta(minutes=85)
    second = runlock.renew(store, "owner", NOW + timedelta(minutes=80))
    assert calendar.local_time(second["expiresAt"]) == NOW + timedelta(minutes=120)
    third = runlock.renew(store, "owner", NOW + timedelta(minutes=119))
    assert third["expiresAt"] == second["expiresAt"]
    assert store.saves == [("owner", False)] * 3
    with pytest.raises(LedgerError, match="expired"):
        runlock.renew(store, "owner", NOW + timedelta(minutes=120))


@pytest.mark.parametrize("holder,minutes", [("other", 1), ("owner", 45), ("owner", 46)])
def test_renewal_cannot_revive_or_steal(tmp_path, holder, minutes):
    store = LeaseStore(tmp_path)
    before = (tmp_path / "locks/run.lock").read_bytes()
    with pytest.raises(LedgerError):
        runlock.renew(store, holder, NOW + timedelta(minutes=minutes))
    assert not store.saves
    assert (tmp_path / "locks/run.lock").read_bytes() == before


def test_renewal_checks_expiry_after_transport(tmp_path, monkeypatch):
    store = LeaseStore(tmp_path)
    current = NOW + timedelta(minutes=44)
    class Clock:
        @staticmethod
        def now(zone):
            return current
    def advance():
        nonlocal current
        current += timedelta(minutes=1)
    monkeypatch.setattr(runlock, "datetime", Clock)
    store.before_save = advance
    with pytest.raises(LedgerError, match="expired"):
        runlock.renew(store, "owner")
    assert not store.saves
    assert json.loads((tmp_path / "locks/run.lock").read_text()) == store.lock


def test_runner_renew_keeps_phase(tmp_path, monkeypatch):
    store = LeaseStore(tmp_path)
    atomic_json(tmp_path / ".session.json", dict(kind="morning", runId="current", holder="owner", phase="plan"))
    monkeypatch.setattr(run_session, "LedgerStore", lambda *args: store)
    result = run_session.run(Namespace(kind="morning", phase="renew", dir=tmp_path, remote="unused"),
                             NOW + timedelta(minutes=40))
    assert result["renewed"] and result["phase"] == "plan"
    assert json.loads((tmp_path / ".session.json").read_text())["phase"] == "plan"
    assert store.saves == [("owner", False)]


def test_renew_cli_keeps_phase(tmp_path, monkeypatch, capsys):
    store = LeaseStore(tmp_path)
    atomic_json(tmp_path / ".session.json", dict(kind="morning", runId="current", holder="owner", phase="plan"))
    class Clock:
        @staticmethod
        def now(zone):
            return NOW + timedelta(minutes=40)
    monkeypatch.setattr(run_session, "datetime", Clock)
    monkeypatch.setattr(runlock, "datetime", Clock)
    monkeypatch.setattr(run_session, "LedgerStore", lambda *args: store)
    monkeypatch.setattr(sys, "argv", ["run_session.py", "--kind", "morning", "--phase", "renew", "--dir", str(tmp_path)])
    assert run_session.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["renewed"] and result["phase"] == "plan"
    assert calendar.local_time(result["expiresAt"]) == NOW + timedelta(minutes=85)


def test_dispatch_watch(prepared):
    args, ticket, log, order, lock = prepared
    args.kind = "watch"
    path = args.dir / ".session.json"
    atomic_json(path, json.loads(path.read_text()) | dict(kind="watch", phase="record"))
    lock["kind"] = "watch"
    assert dispatch_check.run(args, NOW)["args"] == order["args"]


def test_dispatch_duplicate_log_identity(prepared):
    args, ticket, log, order, lock = prepared
    note(args.dir / "logs/duplicate.jsonl", RUN)
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        dispatch_check.run(args, NOW)


@pytest.mark.parametrize("mutation", ["owner", "missing", "acquisition"])
def test_renewal_rechecks_owner_before_persistence(tmp_path, mutation):
    store = LeaseStore(tmp_path)
    def change():
        if mutation == "owner":
            store.lock["holder"] = "other"
        elif mutation == "missing":
            store.lock = None
        else:
            store.lock["startedAt"] = (NOW + timedelta(minutes=1)).isoformat()
    store.before_save = change
    with pytest.raises(LedgerError):
        runlock.renew(store, "owner", NOW + timedelta(minutes=40))
    assert not store.saves


def test_reconcile_cli_preserved_primary_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    log = note(tmp_path / "logs" / LIVE_NAME, "2026-11-16-us")
    before = log.path.read_bytes()
    payloads = {
        "history": dict(ret_code=0, ret_msg="success", data=dict(orders=[],
                        pagination=dict(has_more=False, next_key=""))),
        "positions": dict(ret_code=0, ret_msg="success", data=dict(positions=[])),
        "cash": dict(cash=100000, equity=100000),
        "state": PortfolioState(cash=100000).to_dict(),
    }
    command = [sys.executable, "scripts/reconcile.py", "--runtime", str(tmp_path), "--log", str(log.path)]
    for name, payload in payloads.items():
        path = tmp_path / f"{name}.json"
        atomic_json(path, payload)
        command.extend(["--" + name, str(path)])
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert not json.loads(result.stdout).get("halted")
    assert log.path.read_bytes().startswith(before)
    assert all(event["runId"] == "2026-11-16-us" for event in log.read())
