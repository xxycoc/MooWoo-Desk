"""Real local git transport and deterministic runtime gates; no service calls."""

from argparse import Namespace
from datetime import datetime, timedelta
import base64
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from moowoo import calendar
from moowoo.ledger import EventLog, verify
from moowoo.persistence import LedgerError, LedgerStore
from moowoo.runlock import acquire, require_owned

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_session
from qca_deploy import build_payloads, validate_approval

NOW = datetime.fromisoformat("2026-11-17T15:00:00+00:00")


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(path)], capture_output=True, check=True)
    return str(path)


def store(tmp_path, remote, name="runtime"):
    result = LedgerStore(tmp_path / name, remote)
    result.restore()
    return result


def note(repository, name="run", text="test"):
    log = EventLog(repository.directory / f"logs/{name}.jsonl", runId=name)
    log.append("reflection_note", dict(prompt="test", text=text))
    return log


def test_empty_and_roundtrip_cli(tmp_path, remote):
    first = tmp_path / "one"
    def cli(action, path):
        return subprocess.run([sys.executable, "scripts/persist_ledger.py", action,
                               "--dir", str(path), "--remote", remote], cwd=ROOT, capture_output=True, text=True)
    result = cli("restore", first)
    assert result.returncode == 0 and "starting empty" in result.stdout
    payloads = {"state.json": '{"cash":100000}', "tickets/t.json": "{}", "receipts/r.json": "[]",
                "grading/g.json": "{}", "hypotheses/latest.json": "{}"}
    for name, content in payloads.items():
        path = first / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    note(LedgerStore(first, remote))
    assert cli("save", first).returncode == 0
    second = tmp_path / "two"
    assert cli("restore", second).returncode == 0
    for name, content in payloads.items():
        assert (second / name).read_text() == content
    assert verify(second / "logs/run.jsonl").ok
    refs = subprocess.check_output(["git", "--git-dir", remote, "show-ref"], text=True)
    assert "refs/heads/ledger" in refs and "refs/heads/main" not in refs


def test_broken_chain_never_pushes(tmp_path, remote):
    repo = store(tmp_path, remote)
    log = note(repo)
    repo.save("good")
    head = repo.git("rev-parse", "HEAD").stdout
    log.path.write_bytes(log.path.read_bytes().replace(b'"text":"test"', b'"text":"evil"'))
    with pytest.raises(LedgerError, match="broken event chain"):
        repo.save("bad")
    restored = store(tmp_path, remote, "restored")
    assert restored.git("rev-parse", "HEAD").stdout == head
    assert "evil" in log.path.read_text()


def test_credentials_never_on_disk_or_output(tmp_path, remote, monkeypatch, capsys):
    token = "SENTINEL_ledger_secret_123"
    monkeypatch.setenv("GITHUB_LEDGER_TOKEN", token)
    monkeypatch.setenv("GIT_TRACE", "1")
    repo = store(tmp_path, remote)
    note(repo)
    result = repo.save("safe")
    output = capsys.readouterr()
    encoded = base64.b64encode(("x-access-token:" + token).encode()).decode()
    for secret in (token, encoded):
        assert secret not in output.out + output.err + json.dumps(result)
        assert secret not in (repo.directory / ".git/config").read_text()
    original = subprocess.run
    calls = []
    def capture(command, **kwargs):
        calls.append((command, kwargs["env"]))
        result = original(command, **kwargs)
        result.stderr += token + encoded
        return result
    monkeypatch.setattr(subprocess, "run", capture)
    assert token not in repo.git("status").stderr
    assert all(token not in " ".join(command) for command, _ in calls)
    assert all("GIT_TRACE" not in env and "GITHUB_LEDGER_TOKEN" not in env for _, env in calls)


def test_pull_rebase_push_and_conflict_preserves_copy(tmp_path, remote):
    first = store(tmp_path, remote, "first")
    note(first)
    first.save("base")
    second = store(tmp_path, remote, "second")
    (first.directory / "one.json").write_text("1")
    first.save("one")
    (second.directory / "two.json").write_text("2")
    second.save("two")
    first.restore()
    assert (first.directory / "two.json").exists()
    (first.directory / "one.json").write_text("3")
    first.save("three")
    (second.directory / "one.json").write_text("4")
    with pytest.raises(LedgerError, match="rebase conflict"):
        second.save("four")
    assert (second.directory / "one.json").exists()
    assert (second.directory / ".git/rebase-merge").exists()
    assert store(tmp_path, remote, "third").directory.joinpath("one.json").read_text() == "3"


def test_lock_exclusion_release_and_expiry(tmp_path, remote):
    first = store(tmp_path, remote, "first")
    second = store(tmp_path, remote, "second")
    lock = acquire(first, "morning", NOW)
    with pytest.raises(LedgerError, match="lock is held"):
        acquire(second, "watch", NOW)
    require_owned(first, lock["holder"], NOW + timedelta(minutes=44))
    with pytest.raises(LedgerError, match="expired"):
        require_owned(first, lock["holder"], NOW + timedelta(minutes=45))
    takeover = acquire(second, "watch", NOW + timedelta(minutes=45))
    events = [event for path in (second.directory / "logs").glob("*.jsonl") for event in EventLog(path, runId=path.stem).read()]
    assert any("Expired lease" in event.get("text", "") for event in events)
    assert not any(event["type"] == "halt" for event in events)
    with pytest.raises(LedgerError, match="another run"):
        first.save("stale writer", lock["holder"])
    second.save("release", takeover["holder"])
    fresh = store(tmp_path, remote, "third")
    assert not (fresh.directory / "locks/run.lock").exists()
    acquire(fresh, "audit", NOW + timedelta(minutes=46))


def test_acquisition_race_does_not_rebase(tmp_path, remote, monkeypatch):
    first = store(tmp_path, remote, "first")
    second = store(tmp_path, remote, "second")
    original = first.git
    winner = []
    def race(*args, **kwargs):
        if args[0] == "push" and not winner:
            winner.append(acquire(second, "watch", NOW))
        return original(*args, **kwargs)
    monkeypatch.setattr(first, "git", race)
    with pytest.raises(LedgerError, match="lost a race"):
        acquire(first, "morning", NOW)
    require_owned(second, winner[0]["holder"], NOW)


def test_ownership_checks_clock_after_fetch(tmp_path, remote, monkeypatch):
    import moowoo.runlock as runlock
    repo = store(tmp_path, remote)
    lock = acquire(repo, "watch", NOW)
    current = NOW + timedelta(minutes=44)
    class Clock:
        @staticmethod
        def now(zone):
            return current
    monkeypatch.setattr(runlock, "datetime", Clock)
    original = repo.fetch
    def delayed_fetch():
        nonlocal current
        result = original()
        current += timedelta(minutes=1)
        return result
    monkeypatch.setattr(repo, "fetch", delayed_fetch)
    with pytest.raises(LedgerError, match="expired"):
        require_owned(repo, lock["holder"])


@pytest.mark.parametrize("day", (17, 18, 19, 20, 23, 24, 25))
def test_full_days(day):
    day = f"2026-11-{day}"
    assert calendar.is_trading_day(day)
    assert calendar.session_open(day).hour == 9
    assert calendar.session_close(day).hour == 16
    assert calendar.is_regular_hours(calendar.session_open(day))
    assert not calendar.is_regular_hours(calendar.session_close(day))


@pytest.mark.parametrize("day", (14, 21, 22, 26, 28, 29, 30))
def test_nontrading_days(day):
    day = f"2026-11-{day}"
    assert not calendar.is_trading_day(day)
    assert calendar.session_open(day) is calendar.session_close(day) is None
    assert calendar.minutes_since_open(day + "T15:00:00Z") is None


def test_completed_pre_window_session_has_hours_but_no_runs():
    assert not calendar.is_trading_day("2026-11-16")
    assert calendar.session_close("2026-11-16").hour == 16
    assert calendar.minutes_since_open("2026-11-16T15:00:00Z") is None
    assert not calendar.run_allowed("watch", "2026-11-16T15:00:00Z")


def test_half_day_dst_and_audit():
    close = calendar.session_close("2026-11-27")
    assert close.hour == 13
    assert close.astimezone(ZoneInfo("Asia/Singapore")).isoformat() == "2026-11-28T02:00:00+08:00"
    assert calendar.session_open("2026-11-17").astimezone(ZoneInfo("Asia/Singapore")).hour == 22
    assert calendar.local_time("2026-07-01T13:30:00Z").hour == 9  # IANA DST, not a fixed offset
    assert calendar.run_allowed("audit", close + timedelta(minutes=10))
    assert not calendar.run_allowed("audit", close + timedelta(hours=3, minutes=10))
    assert calendar.minutes_since_open("2026-11-17T14:34:59Z") < 5
    assert calendar.minutes_since_open("2026-11-17T14:35:00Z") == 5
    with pytest.raises(ValueError, match="timezone-aware"):
        calendar.is_regular_hours(datetime(2026, 11, 17, 10))


@pytest.mark.parametrize("kind,now", [("morning", "2026-11-17T13:30:00Z"),
    ("watch", "2026-11-26T15:00:00Z"), ("watch", "2026-11-27T18:00:01Z"),
    ("audit", "2026-11-27T21:10:00Z")])
def test_runner_skips_and_persists_unlock(tmp_path, remote, kind, now):
    args = Namespace(kind=kind, phase="start", dir=tmp_path / "runtime", remote=remote)
    result = run_session.run(args, now)
    assert result["skipped"] and result["saved"] and result["unlocked"]
    fresh = store(tmp_path, remote, "restored")
    assert not (fresh.directory / "locks/run.lock").exists()
    assert not list((fresh.directory / "tickets").glob("*"))
    logs = list((fresh.directory / "logs").glob("*.jsonl"))
    assert logs and all(verify(path).ok for path in logs)


def test_runner_requires_sequence_and_lease(tmp_path, remote):
    args = Namespace(kind="morning", phase="start", dir=tmp_path / "runtime", remote=remote)
    started = run_session.run(args, NOW)
    assert started["phase"] == "start"
    args.phase = "prepare"
    with pytest.raises(ValueError, match="not allowed"):
        run_session.run(args, NOW)
    with pytest.raises(LedgerError, match="expired"):
        run_session.run(args, NOW + timedelta(minutes=46))
    args.phase = "abort"
    assert run_session.run(args, NOW + timedelta(minutes=46))["unlocked"]


def test_dry_schedule_payload_and_autonomy(monkeypatch):
    validate_approval(ROOT / "config/rule-ledger.jsonl")
    monkeypatch.setenv("GITHUB_LEDGER_TOKEN", "DO_NOT_PRINT_TOKEN")
    result = subprocess.run([sys.executable, "scripts/qca_deploy.py", "--stage", "schedules",
        "--executor-approval", "allow", "--approval-log", "config/rule-ledger.jsonl"],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "DO_NOT_PRINT_TOKEN" not in result.stdout + result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["approvalDecisionVerified"]
    schedules = [op["body"] for op in manifest["operations"] if op["key"].startswith("schedule.")]
    assert len(schedules) == 5
    assert any("no IM sink" in warning for warning in manifest["warnings"])
    for body in schedules:
        assert body["execution"]["max_concurrent_runs"] == 1
        minutes = 120 if body["name"] == "moowoo-morning" else 25
        assert body["execution"]["timeout_ms"] == minutes * 60 * 1000
        assert body["stop_at"] == "2026-11-28T06:00:00+08:00"
        assert "scripts/run_session.py --kind" in body["initial_events"][0]["content"]
        assert body["sinks"] == []
        assert body["environment_variables"]["GITHUB_LEDGER_TOKEN"] == "${secret.GITHUB_LEDGER_TOKEN}"


def test_executor_dry_stage_and_apply_refusal():
    command = [sys.executable, "scripts/qca_deploy.py", "--stage", "executor",
               "--executor-approval", "allow", "--approval-log", "config/rule-ledger.jsonl"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["approvalDecisionVerified"]
    assert [op["key"] for op in manifest["operations"]] == ["agent.executor"]
    configs = next(tool["configs"] for tool in manifest["operations"][0]["body"]["tools"]
                   if tool["type"] == "mcp_toolset")
    orders = {"sim_trade_input_order", "sim_trade_cancel_order", "sim_trade_modify_order"}
    assert all(item["permission_policy"]["type"] == "always_allow" for item in configs if item["name"] in orders)
    refused = subprocess.run(command + ["--apply"], cwd=ROOT, capture_output=True, text=True)
    assert refused.returncode == 2 and "dry run only" in refused.stderr


def test_push_retries_are_bounded(tmp_path, remote, monkeypatch):
    repo = store(tmp_path, remote)
    note(repo)
    original = repo.git
    pushes = []
    def rejected(*args, **kwargs):
        if args[0] == "push":
            pushes.append(args)
            return subprocess.CompletedProcess(args, 1, "", "synthetic rejection")
        return original(*args, **kwargs)
    monkeypatch.setattr(repo, "git", rejected)
    with pytest.raises(LedgerError, match="three retries"):
        repo.save("retain locally")
    assert len(pushes) == 4
    assert (repo.directory / "logs/run.jsonl").exists()
    assert not any("--force" in args for args in pushes)


@pytest.mark.parametrize("script", ["watch.py", "plan_session.py"])
@pytest.mark.parametrize("now", ["2026-11-26T15:00:00Z", "2026-11-27T18:01:00Z", "2026-11-21T15:00:00Z"])
def test_planning_clis_skip_closed_market_before_loading_state(tmp_path, script, now):
    quotes = tmp_path / "quotes.json"
    quotes.write_text(json.dumps(dict(now=now, sessionDate=now[:10], regularOpen=now,
                                     regularClose="2099-01-01T00:00:00Z")))
    log = tmp_path / "closed.jsonl"
    args = [sys.executable, "scripts/" + script, "--quotes", str(quotes), "--state", "missing",
            "--bars-asof", "2026-11-16", "--log", str(log), "--tickets-dir", str(tmp_path / "tickets")]
    if script == "plan_session.py":
        args += ["--ratings", "missing", "--run-id", "closed"]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["skipped"]
    assert all(event["type"] == "reflection_note" for event in EventLog(log, runId="closed").read())
    assert not (tmp_path / "tickets").exists()


def test_audit_runner_real_subcommands_and_restore(tmp_path, remote, monkeypatch):
    from moowoo.portfolio import PortfolioState
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    args = Namespace(kind="audit", phase="start", dir=tmp_path / "runtime", remote=remote)
    now = "2026-11-27T18:10:00Z"
    context = run_session.run(args, now)
    inputs = Path(context["inputs"])
    (Path(args.dir) / "state.json").write_text(PortfolioState(cash=100000).to_json())
    payloads = {"history": {"ret_code": 0, "ret_msg": "success", "data": {"orders": []},
                            "pagination": {"has_more": False, "next_key": "0"}},
                "positions": {"data": []}, "cash": {"cash": 100000, "equity": 100000},
                "bars": {}, "session": {"barsAsOf": "2026-11-27"}}
    for name, data in payloads.items():
        (inputs / (name + ".json")).write_text(json.dumps(data))
    args.phase = "reconcile"
    assert run_session.run(args, now)["phase"] == "reconcile"
    args.phase = "finish"
    with pytest.raises(ValueError, match="not allowed"):
        run_session.run(args, now)
    for phase in ("grade_calls", "score_hypotheses"):
        args.phase = phase
        assert run_session.run(args, now)["phase"] == phase
    args.phase = "finish"
    result = run_session.run(args, now)
    assert result["saved"] and result["unlocked"]
    restored = store(tmp_path, remote, "restored")
    assert (restored.directory / "hypotheses/latest.json").exists()
    assert (restored.directory / f"handoffs/{context['runId']}.json").exists()
    assert not (restored.directory / "locks/run.lock").exists()


def test_cross_run_reconciliation_routes_fill_to_original_log(tmp_path, remote, monkeypatch):
    from moowoo.execution import preflight, prepare, record
    from moowoo.portfolio import PortfolioState
    from moowoo.tickets import OrderTicket
    from hash_prompts import prompt_version
    from plan_session import frozen_config
    from test_execution import fixture
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    repo = store(tmp_path, remote)
    original_run = "2026-11-17-us"
    log = EventLog(repo.directory / f"logs/{original_run}.jsonl", runId=original_run)
    frozen = frozen_config()
    ticket = OrderTicket(decisionId=original_run + ":AAA", ticker="AAA", side="BUY", qty=50,
        limitPrice=100., sleeve="satellite", kind="drift", stop=94., reason="synthetic",
        configHash=frozen["configHash"], createdTs=calendar.utc_stamp(NOW), estFees=.99, signalAtr=2.)
    state = PortfolioState(cash=100000)
    state.reserve(ticket)
    prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-17\npromptVersion={prompt_version()}\n"
    preflight(fixture("accounts"), state, frozen, prereg, prompt_version(), ["AAA"], log)
    prepared = prepare({ticket.decisionId: ticket}, log)["orders"][0]
    record({ticket.decisionId: ticket}, [prepared | dict(status="placed", response=fixture("placement"))], log)
    (repo.directory / "tickets").mkdir()
    (repo.directory / f"tickets/{original_run}.json").write_text(json.dumps(dict(
        runId=original_run, configHash=frozen["configHash"], tickets=[ticket.to_dict()])))
    (repo.directory / "state.json").write_text(state.to_json())
    repo.save("seed submitted order")
    args = Namespace(kind="audit", phase="start", dir=repo.directory, remote=remote)
    context = run_session.run(args, "2026-11-17T21:10:00Z")
    inputs = Path(context["inputs"])
    for name in ("history", "positions", "cash"):
        (inputs / f"{name}.json").write_text(json.dumps(fixture(name)))
    args.phase = "reconcile"
    result = run_session.run(args, "2026-11-17T21:10:00Z")
    assert not result["halted"]
    assert json.loads((repo.directory / "state.json").read_text())["cash"] == pytest.approx(94999.01)
    assert any(event["type"] == "fill" for event in log.read())
    args.phase = "abort"
    run_session.run(args, "2026-11-17T21:11:00Z")


@pytest.mark.parametrize("started,delay,reason", [
    ("2026-11-17T15:00:00+00:00", 61, "ticket expired"),
    ("2026-11-17T20:59:50+00:00", 10, "market closed"),
])
def test_prepare_rechecks_after_checkpoint_push(tmp_path, remote, monkeypatch, started, delay, reason):
    args = Namespace(kind="watch", phase="start", dir=tmp_path / "runtime", remote=remote)
    current = datetime.fromisoformat(started)
    context = run_session.run(args, current)
    control = Path(args.dir) / ".session.json"
    control.write_text(json.dumps(context | {"phase": "plan"}))
    tickets = Path(args.dir) / f"tickets/{context['runId']}.json"
    tickets.parent.mkdir()
    tickets.write_text(json.dumps({"tickets": [{"createdTs": started, "side": "SELL"}]}))
    # Isolate transport timing; order generation is exercised by the CLI tests.
    monkeypatch.setattr(run_session, "invoke", lambda *a: {"orders": [{"tool": "sim_trade_input_order"}]})
    class Clock:
        @staticmethod
        def now(zone):
            return current
    monkeypatch.setattr(run_session, "datetime", Clock)
    original = LedgerStore.save
    def delayed_save(self, *a, **kw):
        nonlocal current
        result = original(self, *a, **kw)
        current += timedelta(seconds=delay)
        return result
    monkeypatch.setattr(LedgerStore, "save", delayed_save)
    args.phase = "prepare"
    with pytest.raises(ValueError, match=reason):
        run_session.run(args)
    assert json.loads(control.read_text())["phase"] == "plan"
    args.phase = "abort"
    assert run_session.run(args)["unlocked"]


@pytest.mark.parametrize("kind", ["morning", "watch"])
def test_runner_real_preflight_accepts_registered_prompts(tmp_path, remote, monkeypatch, kind):
    from moowoo.portfolio import PortfolioState
    from test_execution import fixture
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    args = Namespace(kind=kind, phase="start", dir=tmp_path / "runtime", remote=remote)
    context = run_session.run(args, NOW)
    Path(context["state"]).write_text(PortfolioState(cash=100000).to_json())
    (Path(context["inputs"]) / "accounts.json").write_text(json.dumps(fixture("accounts")))
    # The real 2026-11-17 addendum is now committed: real preflight must accept it.
    from moowoo.execution import registered_prompt
    registered = registered_prompt((ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8"))
    args.phase = "preflight"
    result = run_session.run(args, NOW)
    assert result["runId"] == context["runId"]
    events = EventLog(context["log"], runId=context["runId"]).read()
    starts = [e for e in events if e["type"] == "run_started"]
    assert starts and starts[-1]["promptVersion"] == registered
    assert not any(e["type"] == "halt" for e in events)
    assert not list((Path(args.dir) / "tickets").glob("*.json"))
    args.phase = "abort"
    assert run_session.run(args, NOW)["unlocked"]


@pytest.mark.parametrize("kind", ["morning", "watch"])
def test_empty_order_session_real_phase_commands(tmp_path, remote, monkeypatch, kind):
    from moowoo.execution import preflight
    from moowoo.portfolio import PortfolioState
    from hash_prompts import prompt_version
    from plan_session import frozen_config
    from test_execution import fixture
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    args = Namespace(kind=kind, phase="start", dir=tmp_path / "runtime", remote=remote)
    context = run_session.run(args, NOW)
    inputs = Path(context["inputs"])
    state = PortfolioState(cash=100000)
    Path(context["state"]).write_text(state.to_json())
    frozen = frozen_config()
    prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-17\npromptVersion={prompt_version()}\n"
    original = run_session.invoke
    def with_synthetic_registration(script, *arguments):
        if script == "preflight.py":
            preflight(fixture("accounts"), state, frozen, prereg, prompt_version(), [],
                      EventLog(context["log"], runId=context["runId"]))
            return {"started": True}
        return original(script, *arguments)
    monkeypatch.setattr(run_session, "invoke", with_synthetic_registration)
    payloads = {"history": {"ret_code": 0, "ret_msg": "success", "data": {"orders": []},
                            "pagination": {"has_more": False, "next_key": "0"}},
                "positions": {"data": []}, "cash": {"cash": 100000, "equity": 100000},
                "quotes": {"now": NOW.isoformat(), "sessionDate": "2026-11-17", "quotes": {}},
                "bars": {}, "session": {"barsAsOf": "2026-11-16"}, "ratings": [], "responses": []}
    for name, value in payloads.items():
        (inputs / f"{name}.json").write_text(json.dumps(value))
    for phase in ("preflight", "reconcile", "plan", "prepare", "record", "reconcile", "finish"):
        args.phase = phase
        result = run_session.run(args, NOW)
        if phase == "prepare":
            assert result["orders"] == []
    assert result["saved"] and result["unlocked"]
    restored = store(tmp_path, remote, "restored")
    handoff = json.loads((restored.directory / f"handoffs/{context['runId']}.json").read_text())
    assert all("\\" not in name for name in handoff["logs"])
    assert not (restored.directory / "locks/run.lock").exists()
