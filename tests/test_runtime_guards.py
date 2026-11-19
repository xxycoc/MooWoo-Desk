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
    monkeypatch.setattr(LedgerStore, "save", lambda *args, **kwargs: dict(saved=True))
    atomic_json(tmp_path / f"inputs/{RUN}/quotes-raw-AAA.json", dict(ret_code=0, ret_msg="success",
        data=dict(snapshot_list=[dict(code="US.AAA", update_time=NOW.timestamp()*1000,
                                     last_price=100, bid_price=99.99, ask_price=100)])))
    args = Namespace(kind="morning", decision_id=ticket.decisionId, dir=tmp_path)
    return args, ticket, log, result["orders"][0], lock


def test_dispatch_exact_prepared_args_and_durable_intent(prepared):
    args, ticket, log, order, lock = prepared
    before = log.path.read_bytes()
    assert dispatch_check.run(args, NOW) == dict(ok=True, decisionId=ticket.decisionId, tool=order["tool"], attempt=1,
        args=order["args"], quoteDeadline="2026-11-17T15:01:00Z")
    assert log.path.read_bytes().startswith(before)
    assert log.read()[-1]["executionAction"] == "dispatch_authorized"
    assert config.STALE_PRICE_SECONDS == 60


@pytest.mark.parametrize("seconds,ok", [(60, True), (61, False), (-1, False), (110, False)])
def test_dispatch_only_selected_ticket_freshness(prepared, seconds, ok):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"tickets/{RUN}.json"
    manifest = json.loads(path.read_text())
    manifest["tickets"].append(ticket.to_dict() | dict(decisionId=RUN + ":BBB", createdTs="2026-11-16T15:00:00Z"))
    atomic_json(path, manifest)
    result = dispatch_check.run(args, NOW + timedelta(seconds=seconds))
    assert result["ok"] is ok
    if not ok:
        assert result["skipped"] == (seconds < 0)
        assert log.read()[-1]["executionAction"] == ("skip" if seconds < 0 else "quote_refresh")


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
    assert dispatch_check.run(args)["retryable"]


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
    assert second["capped"] and third["capped"]
    assert store.saves == [("owner", False)] * 2
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


@pytest.mark.parametrize("day", [16, 21, 22, 26, 28])
def test_audit_requires_competition_day(day):
    assert not calendar.run_allowed("audit", f"2026-11-{day}T21:15:00Z")


@pytest.mark.parametrize("change", ["symbol", "multiple", "crossed", "spread", "price", "missing", "future"])
def test_fresh_quote_refusal_skips_only_ticket(prepared, change):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"inputs/{RUN}/quotes-raw-AAA.json"
    payload = json.loads(path.read_text())
    row = payload["data"]["snapshot_list"][0]
    if change == "symbol": row["code"] = "US.BBB"
    if change == "multiple": payload["data"]["snapshot_list"].append(dict(row))
    if change == "crossed": row["bid_price"] = 101
    if change == "spread": row["bid_price"] = 99
    if change == "price": row.update(bid_price=100.01, ask_price=100.02)
    if change == "future": row["update_time"] += 1000
    atomic_json(path, payload)
    if change == "missing": path.unlink()
    result = dispatch_check.run(args, NOW)
    assert result["ok"] is False and result["skipped"]
    assert log.read()[-1]["executionAction"] == "skip"
    assert not any(event["type"] == "halt" for event in log.read())


@pytest.mark.parametrize("ask,ok", [(99.98, True), (100.0, True), (100.01, False)])
def test_buy_limit_only_needs_to_stay_marketable(prepared, ask, ok):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"inputs/{RUN}/quotes-raw-AAA.json"
    payload = json.loads(path.read_text())
    payload["data"]["snapshot_list"][0].update(bid_price=round(ask - .01, 2), ask_price=ask)
    atomic_json(path, payload)
    result = dispatch_check.run(args, NOW)
    assert result["ok"] is ok
    if ok:
        assert result["args"] == order["args"]


def test_dispatch_old_ticket_with_fresh_source(prepared):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"inputs/{RUN}/quotes-raw-AAA.json"
    payload = json.loads(path.read_text())
    payload["data"]["snapshot_list"][0]["update_time"] += 200000
    atomic_json(path, payload)
    assert dispatch_check.run(args, NOW + timedelta(seconds=200))["ok"]
    with pytest.raises(ValueError, match="resolved"):
        dispatch_check.run(args, NOW + timedelta(seconds=200))


def test_dispatch_rechecks_quote_after_persistence(prepared, monkeypatch):
    args, ticket, log, order, lock = prepared
    current = NOW
    class Clock:
        @staticmethod
        def now(zone): return current
    def save(*args, **kwargs):
        nonlocal current
        current += timedelta(seconds=61)
        return dict(saved=True)
    monkeypatch.setattr(dispatch_check, "datetime", Clock)
    monkeypatch.setattr(LedgerStore, "save", save)
    monkeypatch.setattr(runlock, "datetime", Clock)
    result = dispatch_check.run(args)
    assert result["retryable"]
    assert log.read()[-1]["executionAction"] == "quote_refresh"


@pytest.mark.parametrize("received", [False, True])
def test_abort_retains_uncertain_handoff_and_records_saved_receipt(prepared, received):
    args, ticket, log, order, lock = prepared
    state = PortfolioState(cash=100000)
    state.reserve(ticket)
    atomic_json(args.dir / "state.json", state.to_dict())
    assert dispatch_check.run(args, NOW)["ok"]
    if received:
        atomic_json(args.dir / f"inputs/{RUN}/responses.json",
                    [order | dict(status="placed", response=fixture("placement"))])
    log.append("halt", dict(reason="synthetic later failure", scope="run"))
    run_session.run(Namespace(kind="morning", phase="abort", dir=args.dir, remote=run_session.REMOTE), NOW)
    saved = json.loads((args.dir / "state.json").read_text())
    assert [t["decisionId"] for t in saved["pendingTickets"]] == [ticket.decisionId]
    assert len([e for e in log.read() if e["type"] == "order_submitted"]) == int(received)
    assert not any(e.get("executionAction") == "skip" for e in log.read())


def test_dispatch_stale_cli_is_successful_ticket_skip(prepared, monkeypatch, capsys):
    args, ticket, log, order, lock = prepared
    class Clock:
        @staticmethod
        def now(zone): return NOW + timedelta(seconds=61)
    monkeypatch.setattr(dispatch_check, "datetime", Clock)
    monkeypatch.setattr(runlock, "datetime", Clock)
    monkeypatch.setattr(sys, "argv", ["dispatch_check.py", "--kind", "morning", "--decision-id", ticket.decisionId,
                                    "--dir", str(args.dir)])
    assert dispatch_check.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False and output["retryable"]
    assert dispatch_check.main() == 0
    assert json.loads(capsys.readouterr().out)["skipped"]


def test_dispatch_rejects_noninteger_prepared_attempt(prepared):
    args, ticket, log, order, lock = prepared
    log.append("reflection_note", dict(prompt="Execution", text="prepared", executionAction="prepared",
        attempt="1", ticketHash=ticket.ticketHash), decisionId=ticket.decisionId)
    with pytest.raises(ValueError, match="must be integer"):
        dispatch_check.run(args, NOW)


def test_capped_runner_does_not_claim_extension(tmp_path, monkeypatch):
    store = LeaseStore(tmp_path)
    expiry = (NOW + timedelta(minutes=120)).isoformat()
    store.lock["expiresAt"] = expiry
    atomic_json(tmp_path / ".session.json", dict(kind="morning", runId="current", holder="owner",
        phase="record", expiresAt=expiry))
    monkeypatch.setattr(run_session, "LedgerStore", lambda *args: store)
    result = run_session.run(Namespace(kind="morning", phase="renew", dir=tmp_path, remote="unused"),
                             NOW + timedelta(minutes=115))
    assert result["capped"] and not result["renewed"]
    assert result["phase"] == "record" and not store.saves


def test_quote_source_cannot_gain_another_ticket_lifetime(prepared):
    args, ticket, log, order, lock = prepared
    path = args.dir / f"inputs/{RUN}/quotes-raw-AAA.json"
    payload = json.loads(path.read_text())
    payload["data"]["snapshot_list"][0]["update_time"] -= 55000
    atomic_json(path, payload)
    # Ticket is only 55 seconds old, but its quote source is now 110 seconds old.
    result = dispatch_check.run(args, NOW + timedelta(seconds=55))
    assert result["ok"] is False and result["retryable"]
    result = dispatch_check.run(args, NOW + timedelta(seconds=55))
    assert result["skipped"]
    assert result["quoteDeadline"] == "2026-11-17T15:00:05Z"


def test_sell_keeps_existing_exit_spread_exemption(prepared):
    from moowoo.tickets import to_sim_order
    from moowoo.fees import estimate_fees
    args, ticket, log, order, lock = prepared
    sell = OrderTicket(**(ticket.to_dict() | dict(side="SELL", estFees=estimate_fees("SELL", ticket.qty), ticketHash="")))
    atomic_json(args.dir / f"tickets/{RUN}.json", dict(runId=RUN, configHash=ticket.configHash, tickets=[sell.to_dict()]))
    order["args"] = to_sim_order(sell)
    atomic_json(args.dir / f"receipts/{RUN}/prepare-test.json", dict(orders=[order]))
    log.append("reflection_note", dict(prompt="Execution", text="prepared", executionAction="prepared",
        attempt=1, ticketHash=sell.ticketHash), decisionId=ticket.decisionId)
    atomic_json(args.dir / f"inputs/{RUN}/quotes-raw-AAA.json", dict(ret_code=0, ret_msg="success",
        data=dict(snapshot_list=[dict(code="US.AAA", update_time=NOW.timestamp()*1000,
                                     last_price=100, bid_price=100, ask_price=101)])))
    assert dispatch_check.run(args, NOW)["ok"]


def test_sell_skips_when_bid_falls_below_limit(prepared):
    from moowoo.tickets import to_sim_order
    from moowoo.fees import estimate_fees
    args, ticket, log, order, lock = prepared
    sell = OrderTicket(**(ticket.to_dict() | dict(side="SELL", estFees=estimate_fees("SELL", ticket.qty), ticketHash="")))
    atomic_json(args.dir / f"tickets/{RUN}.json", dict(runId=RUN, configHash=ticket.configHash, tickets=[sell.to_dict()]))
    order["args"] = to_sim_order(sell)
    atomic_json(args.dir / f"receipts/{RUN}/prepare-test.json", dict(orders=[order]))
    log.append("reflection_note", dict(prompt="Execution", text="prepared", executionAction="prepared",
        attempt=1, ticketHash=sell.ticketHash), decisionId=ticket.decisionId)
    atomic_json(args.dir / f"inputs/{RUN}/quotes-raw-AAA.json", dict(ret_code=0, ret_msg="success",
        data=dict(snapshot_list=[dict(code="US.AAA", update_time=NOW.timestamp()*1000,
                                     last_price=100, bid_price=99.99, ask_price=100.05)])))
    assert dispatch_check.run(args, NOW)["ok"] is False

@pytest.mark.parametrize("history_mode", ["absent", "missing_page", "later_page_match"])
def test_runtime_releases_only_with_complete_absent_history(prepared, history_mode, monkeypatch):
    class Clock:
        @staticmethod
        def now(zone): return NOW + timedelta(minutes=2)
    monkeypatch.setattr("moowoo.execution.datetime", Clock)
    args, ticket, log, order, lock = prepared
    assert dispatch_check.run(args, NOW)["ok"]
    state = PortfolioState(cash=100000)
    state.reserve(ticket)
    atomic_json(args.dir / "state.json", state.to_dict())
    inputs = args.dir / "inputs" / RUN
    atomic_json(inputs / "handoffs.json", [dict(decisionId=ticket.decisionId, attempt=1, status="approval_expired")])
    history = fixture("history")
    page = deepcopy(history)
    history["data"]["orders"] = []
    if history_mode != "absent":
        history["pagination"] = dict(has_more=True, next_key="page2")
    atomic_json(inputs / "history.json", history)
    atomic_json(inputs / "positions.json", dict(data=[]))
    atomic_json(inputs / "cash.json", dict(cash=100000, equity=100000))
    pages = inputs / "history-pages.json"
    atomic_json(pages, {"page2": page} if history_mode == "later_page_match" else {})
    current = note(args.dir / "logs/next-run.jsonl", "next-run")
    call = Namespace(runtime=args.dir, history=inputs / "history.json", history_pages=pages,
        positions=inputs / "positions.json", cash=inputs / "cash.json", state=args.dir / "state.json")
    if history_mode != "absent":
        with pytest.raises(ValueError, match="missing page|unrecorded order"):
            reconcile_cli.run(call, current)
        assert json.loads(call.state.read_text())["pendingTickets"]
        assert not any(e.get("executionAction") == "skip" for e in log.read())
    else:
        assert not reconcile_cli.run(call, current)["halted"]
        saved = json.loads(call.state.read_text())
        assert saved["pendingTickets"] == []
        assert saved["ticketedDecisionIds"] == [ticket.decisionId]
        assert log.read()[-1]["executionAction"] == "skip"
        count = len(log.read())
        assert not reconcile_cli.run(call, current)["halted"]
        assert len(log.read()) == count
