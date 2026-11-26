"""Synthetic, PROVISIONAL broker responses. No broker/network calls."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo import broker_fields
from moowoo.broker import parse_accounts, parse_cash, parse_history, parse_positions, snapshot_to_state
from moowoo.drills import mcp_timeout
from moowoo.execution import preflight, prepare, record, reconcile, registered_prompt
from moowoo.fees import estimate_fees
from moowoo.ledger import EventLog, verify
from moowoo.portfolio import PortfolioState
from moowoo.tickets import OrderTicket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hash_prompts import prompt_version
from plan_session import frozen_config
from qca_deploy import build_payloads
import watch as watcher
from _execution import command
from types import SimpleNamespace

RUN = "2026-11-17-us"
NOW = "2026-11-17T15:00:00Z"


def fixture(name):
    if name == "history":
        name = "history_filled"
    if name == "placement":
        return json.loads((ROOT / "fixtures/broker/real_sim_trade_input_order.json").read_text())["response"]
    return json.loads((ROOT / f"fixtures/broker/provisional_{name}.json").read_text())


def save(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def synthetic_account(monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")


@pytest.fixture
def setup(tmp_path):
    frozen = frozen_config()
    ticket = OrderTicket(decisionId=RUN+":AAA", ticker="AAA", side="BUY", qty=50,
        limitPrice=100., sleeve="satellite", kind="drift", stop=94., reason="synthetic",
        configHash=frozen["configHash"], createdTs=NOW, estFees=.99, signalAtr=2.)
    log = EventLog(tmp_path / f"{RUN}.jsonl")
    state = PortfolioState(cash=100000)
    state.reserve(ticket)
    prereg = f"configHash: {frozen['configHash']}\n## Addendum 2026-11-17\npromptVersion={prompt_version()}\n"
    return ticket, log, state, prereg


def start(setup):
    ticket, log, state, prereg = setup
    preflight(fixture("accounts"), state, frozen_config(), prereg, prompt_version(), ["AAA"], log)
    return ticket, log, state


def submit(setup):
    ticket, log, state = start(setup)
    prepared = prepare({ticket.decisionId: ticket}, log)["orders"][0]
    record({ticket.decisionId: ticket}, [prepared | dict(status="placed", response=fixture("placement"))], log)
    return ticket, log, state


def snapshots(qty, status=None):
    history, positions, cash = fixture("history"), fixture("positions"), fixture("cash")
    history["data"]["orders"][0].update(cum_qty=str(qty), avg_fill_price="100" if qty else "0",
                                       status=2 if status is None else status)
    positions["data"][0]["qty"] = qty
    cash.update(cash=100000-qty*100-(.99 if qty else 0), equity=100000-(.99 if qty else 0))
    return parse_history(history), parse_positions(positions), parse_cash(cash)


def test_preflight_good(setup):
    _, log, _ = start(setup)
    event = log.read()[-1]
    assert event["type"] == "run_started" and event["trdEnv"] == "SIMULATE"
    assert event["cash"] == event["equity"] == 100000


@pytest.mark.parametrize("bad", ["missing", "ordinary", "market", "title", "config", "prompt", "halted", "prompt_changed"])
def test_preflight_halts_through_command(setup, tmp_path, monkeypatch, bad):
    _, log, state, prereg = setup
    accounts, frozen = fixture("accounts"), frozen_config()
    if bad == "missing": accounts.clear()
    elif bad == "ordinary": accounts[0]["account_type"] = 1
    elif bad == "market": accounts[0]["market_id"] = 99
    elif bad == "title": accounts[0]["account_title"] = "Ordinary paper"
    elif bad == "config": frozen["configHash"] = "0"*64
    elif bad == "prompt": prereg = "no addendum"
    elif bad == "halted": state.halted = True
    elif bad == "prompt_changed": prereg = prereg.replace(prompt_version(), "0"*64)
    args = SimpleNamespace(log=log.path)
    code = command(args, lambda args, locked: preflight(accounts, state, frozen, prereg, prompt_version(), ["AAA"], locked))
    assert code == 2
    assert log.read()[-1]["type"] == "halt"
    if bad == "prompt": assert log.read()[-1]["reason"] == "prompts not pre-registered"


def test_latest_addendum_only():
    assert registered_prompt("## Addendum 2026-11-17\npromptVersion="+"a"*64) == "a"*64
    with pytest.raises(ValueError):
        registered_prompt("## Addendum 2026-11-17\npromptVersion="+"a"*64+"\n## Addendum 2026-11-18\npending")


def test_broker_required_and_optional(monkeypatch):
    assert parse_accounts(fixture("accounts"))[0]["accountType"] == 2
    # Live shape seen in the 17 Nov morning run.
    wrapped = {"ret_code": 0, "ret_msg": "success", "data": {"accounts": fixture("accounts")}}
    assert parse_accounts(wrapped)[0]["accountType"] == 2
    with pytest.raises(ValueError, match="ret_code 1"):
        parse_accounts({"ret_code": 1, "ret_msg": "denied", "data": {}})
    assert parse_cash(fixture("cash"))["cash"] == 94999.01
    for parser, name, field in ((parse_accounts, "accounts", "account_type"),
                                (parse_positions, "positions", "qty"),
                                (parse_history, "history", "cum_qty")):
        payload = fixture(name)
        row = payload[0] if name == "accounts" else payload["data"]["orders"][0] if name == "history" else payload["data"][0]
        del row[field]
        with pytest.raises(ValueError, match="required"):
            parser(payload)
    with pytest.raises(ValueError): parse_cash({"cash": 5})
    changed = {"ret_code": 0, "ret_msg": "success", "data": {"settled_cash": 94999.01, "total_asset": 99999.01, "hold": 0}}
    monkeypatch.setitem(broker_fields.CASH_INFO["required"], "cash", "settled_cash")
    assert parse_cash(changed)["cash"] == 94999.01


def test_snapshot_identity(setup):
    ticket, _, state, _ = setup
    state.positions["AAA"] = dict(qty=3, avgCost=90, kind="drift", sleeve="satellite",
                                  decisionId=ticket.decisionId, stop=94, entryDate="2026-11-17")
    rebuilt = snapshot_to_state(parse_positions(fixture("positions")), parse_cash(fixture("cash")), state)
    assert rebuilt.positions["AAA"]["qty"] == 50
    assert rebuilt.positions["AAA"]["stop"] == 94
    assert state.positions["AAA"]["qty"] == 3
    state.positions["AAA"]["decisionId"] = "other:AAA"
    with pytest.raises(ValueError, match="identity"):
        snapshot_to_state(parse_positions(fixture("positions")), parse_cash(fixture("cash")), state)


def test_prepare_idempotency(setup):
    ticket, log, _ = submit(setup)
    assert not prepare({ticket.decisionId: ticket}, log)["orders"]
    assert len([event for event in log.read() if event["type"] == "order_submitted"]) == 1


@pytest.mark.parametrize("field", ["acc_id", "market", "symbol", "order_type", "order_side", "qty", "price", "order_trade_time_type", "text", "extra"])
def test_record_field_mismatch_halts(setup, field):
    ticket, log, _ = start(setup)
    request = prepare({ticket.decisionId: ticket}, log)["orders"][0]
    request["args"][field] = "wrong"
    request.update(status="placed", response=fixture("placement"))
    result = command(SimpleNamespace(log=log.path), lambda args, locked: record({ticket.decisionId: ticket}, [request], locked))
    assert result == 2 and log.read()[-1]["type"] == "halt"
    assert not any(event["type"] == "order_submitted" for event in log.read())
    assert "synthetic-paper-account" not in log.path.read_text()


def test_timeout_once_then_skip(setup):
    ticket, log, _ = start(setup)
    tickets = {ticket.decisionId: ticket}
    first = prepare(tickets, log)["orders"][0]
    assert not prepare(tickets, log)["orders"]
    failure = first | dict(status="timeout", reason="synthetic timeout")
    record(tickets, [failure], log)
    assert not prepare(tickets, log)["orders"]
    record(tickets, [failure | dict(absenceConfirmed=True)], log)
    second = prepare(tickets, log)["orders"][0]
    assert second["attempt"] == 2 and second["decisionId"] == first["decisionId"]
    record(tickets, [second | dict(status="timeout", reason="again", absenceConfirmed=True)], log)
    assert not prepare(tickets, log)["orders"]
    assert log.read()[-1]["executionAction"] == "skip"
    assert mcp_timeout(ticket.decisionId, log)["pass"]


def test_approval_expired_skips(setup):
    ticket, log, _ = start(setup)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    record(tickets, [request | dict(status="approval_expired", reason="session closed")], log)
    assert not prepare(tickets, log)["orders"]
    state = setup[2]
    updated, result = reconcile(tickets, [], [], dict(cash=100000, equity=100000), state, log)
    assert not result["halted"] and not updated.pendingTickets
    assert ticket.decisionId in updated.ticketedDecisionIds


@pytest.mark.parametrize("qty", [0, 20, 50])
def test_reconcile_full_partial_unfilled_and_replay(setup, qty):
    ticket, log, state = submit(setup)
    history, positions, cash = snapshots(qty)
    updated, result = reconcile({ticket.decisionId: ticket}, history, positions, cash, state, log)
    assert not result["halted"]
    assert updated.cash == cash["cash"]
    assert bool(result["cancel"]) == (qty < 50)
    if qty < 50:
        assert result["cancel"][0]["remainingQty"] == 50-qty
        assert result["cancel"][0]["args"]["order_id"] == "3164623"
    count = len(log.read())
    replay, _ = reconcile({ticket.decisionId: ticket}, history, positions, cash, updated, log)
    assert replay.to_dict() == updated.to_dict() and len(log.read()) == count
    if qty == 20:
        completed, result = reconcile({ticket.decisionId: ticket}, *snapshots(50), updated, log)
        assert completed.cash == pytest.approx(94999.01)
        assert completed.positions["AAA"]["qty"] == 50
        assert not result["cancel"] and not completed.pendingTickets


@pytest.mark.parametrize("difference", ["cash", "position", "extra_position", "missing_position"])
def test_unexplained_difference_halts(setup, difference):
    ticket, log, state = submit(setup)
    history, positions, cash = snapshots(50)
    if difference == "cash": cash["cash"] += 2; cash["equity"] += 2
    elif difference == "position": positions[0]["qty"] += 1; cash["equity"] += 100
    elif difference == "extra_position": positions.append(positions[0] | dict(ticker="BBB")); cash["equity"] += 5000
    else: positions.clear(); cash["equity"] -= 5000
    updated, result = reconcile({ticket.decisionId: ticket}, history, positions, cash, state, log)
    assert updated.halted and result["diff"]
    assert log.read()[-1]["type"] == "halt" and log.read()[-1]["diff"]


def test_sell_partial_fee_deltas_and_replay(setup):
    entry, log, state, prereg = setup
    state.pendingTickets = []
    state.ticketedDecisionIds = []
    state.positions["AAA"] = dict(qty=50, avgCost=100, sleeve="satellite", kind="drift",
        stop=94, entryPrice=100, entryDate="2026-11-16", decisionId="prior:AAA")
    state.cash = 95000
    ticket = OrderTicket(**(entry.body() | dict(side="SELL", estFees=estimate_fees("SELL", 50))))
    state.reserve(ticket)
    preflight(fixture("accounts"), state, frozen_config(), prereg, prompt_version(), ["AAA"], log)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    record(tickets, [request | dict(status="placed", response=fixture("placement"))], log)
    for quantity in (20, 35, 50):
        history = fixture("history")
        history["data"]["orders"][0].update(side=2, cum_qty=str(quantity), status=2)
        positions = fixture("positions")
        positions["data"][0].update(qty=50-quantity, text="prior:AAA")
        cash = dict(cash=95000+quantity*100-estimate_fees("SELL", quantity),
                    equity=100000-estimate_fees("SELL", quantity))
        history, positions, cash = parse_history(history), parse_positions(positions), parse_cash(cash)
        state, result = reconcile(tickets, history, positions, cash, state, log)
        assert not result["halted"]
        assert state.cash == pytest.approx(cash["cash"])
        count = len(log.read())
        replay, _ = reconcile(tickets, history, positions, cash, state, log)
        assert replay.to_dict() == state.to_dict() and len(log.read()) == count


def test_ambiguous_history_cannot_guess_entry_identity(setup):
    ticket, log, state = submit(setup)
    history, positions, cash = snapshots(50)
    positions[0].pop("decisionId", None)
    history.append(history[0] | dict(orderId="older-order", decisionId="older:AAA"))
    updated, result = reconcile({ticket.decisionId: ticket}, history, positions, cash, state, log)
    assert updated.halted and "unmatched strategy identity" in result["diff"]["snapshot"]


def test_reconcile_counts_submissions_across_run_logs(setup):
    ticket, log, state = submit(setup)
    state.execution["orders"] = {"other-order": "2026-11-17"}
    state.ordersPlacedThisSession = 1
    updated, result = reconcile({ticket.decisionId: ticket}, *snapshots(50), state, log)
    assert not result["halted"] and updated.ordersPlacedThisSession == 2


def test_cancelled_partial_has_no_cancel(setup):
    ticket, log, state = submit(setup)
    record({ticket.decisionId: ticket}, [dict(decisionId=ticket.decisionId, tool="sim_trade_cancel_order",
        args=dict(acc_id="synthetic-paper-account", market=100, order_id="3164623"),
        response=fixture("cancel"))], log)
    updated, result = reconcile({ticket.decisionId: ticket}, *snapshots(20), state, log)
    assert not result["cancel"] and not updated.pendingTickets


def test_incomplete_history_fails():
    payload = fixture("history") | dict(pagination=dict(has_more=True, next_key="more"))
    with pytest.raises(ValueError, match="incomplete"): parse_history(payload)


def test_log_lock_blocks_concurrent_writer(tmp_path):
    log = EventLog(tmp_path / f"{RUN}.jsonl")
    script = "from moowoo.ledger import EventLog; EventLog(__import__('sys').argv[1], lock_timeout=.1).append('reflection_note', dict(prompt='test', text='writer'))"
    with log.locked():
        process = subprocess.run([sys.executable, "-c", script, str(log.path)], cwd=ROOT, capture_output=True, text=True)
        assert process.returncode != 0 and "lock timeout" in process.stderr
    log.append("reflection_note", dict(prompt="test", text="released"))
    assert verify(log.path).ok and not log.path.with_suffix(".jsonl.lock").exists()


def test_deploy_approval_override():
    for mode in ("ask", "allow"):
        manifest = build_payloads(executor_approval=mode)
        for operation in manifest["operations"]:
            if not operation["key"].startswith("agent."): continue
            role = operation["key"].split(".")[1]
            configs = next(tool["configs"] for tool in operation["body"]["tools"] if tool["type"] == "mcp_toolset")
            for tool in configs:
                if tool["name"] in ("sim_trade_input_order", "sim_trade_cancel_order", "sim_trade_modify_order"):
                    assert tool["permission_policy"]["type"] == ("always_"+mode if role == "executor" else "always_deny")
    process = subprocess.run([sys.executable, "scripts/qca_deploy.py", "--executor-approval", "allow"], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0 and json.loads(process.stdout)["executorApproval"] == "allow"


def test_watch_stop_and_replay(tmp_path):
    state = PortfolioState(cash=95000, positions={"AAA": dict(qty=50, avgCost=100, sleeve="satellite",
        kind="drift", entryDate="2026-11-16", entryPrice=100, decisionId="prior:AAA", stop=94, signalAtr=2)})
    state_path = save(tmp_path / "state.json", state.to_dict())
    quote_path = save(tmp_path / "quotes.json", dict(sessionDate="2026-11-17", now=NOW,
        regularOpen="2026-11-17T14:30:00Z", regularClose="2026-11-17T21:00:00Z",
        quotes={"AAA": dict(last=93, bid=92.9, ask=93.1, ts=NOW)}))
    bars_path = save(tmp_path / "bars.json", {"AAA": [dict(date="2026-11-16", open=100, high=101, low=99, close=100, volume=100000)]})
    args = [sys.executable, "scripts/watch.py", "--state", state_path, "--quotes", quote_path,
            "--bars-asof", "2026-11-16", "--bars", bars_path, "--log", str(tmp_path / f"{RUN}.jsonl"),
            "--tickets-dir", str(tmp_path / "tickets")]
    for _ in range(2):
        process = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
        assert process.returncode == 0, process.stdout+process.stderr
    events = EventLog(tmp_path / f"{RUN}.jsonl").read()
    assert len([event for event in events if event["type"] == "stop_hit"]) == 1
    saved = json.loads(Path(state_path).read_text())
    assert saved["positions"]["AAA"]["stop"] >= 94
    assert len(saved["pendingTickets"]) == 1


def test_watch_trail_persists_and_never_loosens(tmp_path):
    state = PortfolioState(cash=95000, positions={"AAA": dict(qty=50, avgCost=100, sleeve="satellite",
        kind="drift", entryDate="2026-11-16", entryPrice=100, decisionId="prior:AAA", stop=94, signalAtr=2)})
    state_path = save(tmp_path / "state.json", state.to_dict())
    quote_path = save(tmp_path / "quotes.json", dict(sessionDate="2026-11-17", now=NOW,
        regularOpen="2026-11-17T14:30:00Z", regularClose="2026-11-17T21:00:00Z",
        quotes={"AAA": dict(last=110, bid=109.9, ask=110.1, ts=NOW)}))
    bars_path = save(tmp_path / "bars.json", {"AAA": [dict(date="2026-11-16", open=100,
        high=109, low=99, close=108, volume=100000)]})
    log = EventLog(tmp_path / f"{RUN}.jsonl")
    args = SimpleNamespace(state=state_path, quotes=quote_path, bars=bars_path,
        bars_asof="2026-11-16", tickets_dir=tmp_path / "tickets", log=log.path)
    assert command(args, watcher.run, persist_halt=True) == 0
    first_stop = json.loads(Path(state_path).read_text())["positions"]["AAA"]["stop"]
    assert first_stop > 94
    quotes = json.loads(Path(quote_path).read_text())
    quotes["quotes"]["AAA"].update(last=first_stop+1, bid=first_stop+.9, ask=first_stop+1.1)
    save(Path(quote_path), quotes)
    assert command(args, watcher.run, persist_halt=True) == 0
    assert json.loads(Path(state_path).read_text())["positions"]["AAA"]["stop"] == first_stop


def test_execution_cli_pipeline(setup, tmp_path):
    ticket, log, state = start(setup)
    tickets_path = save(tmp_path / "tickets.json", dict(runId=RUN, configHash=ticket.configHash, tickets=[ticket.to_dict()]))
    base = [sys.executable, "scripts/execute_tickets.py"]
    suffix = ["--tickets", tickets_path, "--log", str(log.path)]
    process = subprocess.run(base+["prepare"]+suffix, cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stdout+process.stderr
    order = json.loads(process.stdout)["orders"][0]
    receipt = save(tmp_path / "responses.json", [order | dict(status="placed", response=fixture("placement"))])
    process = subprocess.run(base+["record"]+suffix+["--responses", receipt], cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stdout+process.stderr
    state_path = save(tmp_path / "state.json", state.to_dict())
    args = [sys.executable, "scripts/reconcile.py", "--state", state_path]+suffix
    for name in ("history", "positions", "cash"):
        fixture_name = "history_filled" if name == "history" else name
        args += ["--"+name, str(ROOT / f"fixtures/broker/provisional_{fixture_name}.json")]
    process = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stdout+process.stderr
    assert json.loads(Path(state_path).read_text())["cash"] == pytest.approx(94999.01)


def test_preregistration_requires_addendum_and_matches_current_prompts():
    text = (ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8")
    # Without the dated addendum, prompts count as unregistered.
    without = text.split("\n## 9. Addendum")[0]
    with pytest.raises(ValueError, match="prompts not pre-registered"):
        registered_prompt(without)
    # The committed 2026-11-17 freeze must match the prompts actually deployed;
    # editing a prompt without a new dated addendum fails here.
    assert registered_prompt(text) == prompt_version()


def test_session_info_uses_frozen_calendar():
    import subprocess, sys, json as _json
    from moowoo.calendar import previous_session
    assert previous_session("2026-11-17").isoformat() == "2026-11-16"
    assert previous_session("2026-11-27").isoformat() == "2026-11-25"
    out = subprocess.run([sys.executable, str(ROOT / "scripts/session_info.py"), "--now", "2026-11-17T15:00:00Z"],
                         capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL).stdout
    facts = _json.loads(out)
    assert facts["barsAsOf"] == "2026-11-16" and facts["regularHours"] and facts["minutesSinceOpen"] == 30
    assert facts["barsAsOfOpen"] == "2026-11-16T14:30:00Z" and facts["barsAsOfClose"] == "2026-11-16T21:00:00Z"
    from moowoo.calendar import is_regular_hours, run_allowed
    assert not is_regular_hours("2026-11-16T15:00:00Z") and not run_allowed("morning", "2026-11-16T15:00:00Z")

@pytest.mark.parametrize("age,status,attempt,complete,released", [
    (901, None, 1, True, True),
    (900, None, 1, True, False),
    (899, None, 1, True, False),
    (-1, None, 1, True, False),
    (0, "approval_expired", 1, True, True),
    (0, "not_submitted", 1, True, True),
    (0, "timeout", 1, True, False),
    (0, "approval_expired", 2, True, False),
    (0, "approval_expired", True, True, False),
    (901, "submitted", 1, True, False),
    (901, "placed", 1, True, False),
    (901, "approval_expired", 1, False, False),
])
def test_reconcile_expired_authorization(setup, age, status, attempt, complete, released):
    from datetime import datetime, timedelta
    from moowoo.execution import note, release_undispatched
    ticket, log, state = start(setup)
    tickets = {ticket.decisionId: ticket}
    prepare(tickets, log)
    note(log, ticket, "dispatch_authorized", attempt=1, ticketHash=ticket.ticketHash, quoteDeadline=NOW)
    handoffs = [] if status is None else [dict(decisionId=ticket.decisionId, attempt=attempt, status=status)]
    now = datetime.fromisoformat(NOW.replace("Z", "+00:00")) + timedelta(seconds=age)
    # Abort before reconciliation must retain an uncertain authorization.
    assert release_undispatched(tickets, state, log) == []
    kwargs = dict(history_complete=complete, handoffs=handoffs, now=now)
    updated, result = reconcile(tickets, [], [], dict(cash=100000, equity=100000), state, log, **kwargs)
    assert not result["halted"]
    assert bool(updated.pendingTickets) is not released
    assert updated.reservedCash == (0 if released else state.reservedCash)
    assert updated.ticketedDecisionIds == [ticket.decisionId]
    skips = [e for e in log.read() if e.get("executionAction") == "skip"]
    assert len(skips) == int(released)
    if released:
        assert skips[0]["reason"] == "authorization expired before handoff; never submitted"
        assert prepare(tickets, log)["orders"] == []
    before = len(log.read())
    again, result = reconcile(tickets, [], [], dict(cash=100000, equity=100000), updated, log, **kwargs)
    assert again.to_dict() == updated.to_dict()
    assert len(log.read()) == before
    release_undispatched(tickets, again, log)
    assert bool(again.pendingTickets) is not released


@pytest.mark.parametrize("deadline", [None, "bad", "2026-11-17T15:00:00"])
def test_reconcile_invalid_deadline_stays_pending(setup, deadline):
    from moowoo.execution import note
    ticket, log, state = start(setup)
    note(log, ticket, "dispatch_authorized", attempt=1, ticketHash=ticket.ticketHash, quoteDeadline=deadline)
    updated, _ = reconcile({ticket.decisionId: ticket}, [], [], dict(cash=100000, equity=100000),
                           state, log, history_complete=True)
    assert updated.pendingTickets == state.pendingTickets


def test_reconcile_older_attempt_cannot_release_new_authorization(setup):
    from moowoo.execution import note
    ticket, log, state = start(setup)
    for attempt, deadline in [(1, "2020-01-01T00:00:00Z"), (2, "2099-01-01T00:00:00Z")]:
        note(log, ticket, "dispatch_authorized", attempt=attempt, ticketHash=ticket.ticketHash, quoteDeadline=deadline)
    updated, _ = reconcile({ticket.decisionId: ticket}, [], [], dict(cash=100000, equity=100000), state, log,
        history_complete=True, handoffs=[dict(decisionId=ticket.decisionId, attempt=1, status="approval_expired")])
    assert updated.pendingTickets == state.pendingTickets


def test_reconcile_submitted_authorization_remains_pending(setup):
    from moowoo.execution import note
    ticket, log, state = submit(setup)
    note(log, ticket, "dispatch_authorized", attempt=1, ticketHash=ticket.ticketHash, quoteDeadline=NOW)
    updated, _ = reconcile({ticket.decisionId: ticket}, *snapshots(0), state, log,
        history_complete=True, handoffs=[dict(decisionId=ticket.decisionId, attempt=1, status="approval_expired")])
    assert updated.pendingTickets
    assert not any(e.get("executionAction") == "skip" for e in log.read())


def test_record_expired_receipt_after_reconcile_is_idempotent(setup):
    from moowoo.execution import note, release_undispatched
    ticket, log, state = start(setup)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    note(log, ticket, "dispatch_authorized", attempt=1, ticketHash=ticket.ticketHash, quoteDeadline=NOW)
    updated, _ = reconcile(tickets, [], [], dict(cash=100000, equity=100000), state, log,
                           history_complete=True, handoffs=[request | dict(status="approval_expired")])
    response = request | dict(status="approval_expired", reason="never submitted")
    record(tickets, [response], log)
    before = len(log.read())
    record(tickets, [response], log)
    release_undispatched(tickets, updated, log)
    release_undispatched(tickets, updated, log)
    assert len(log.read()) == before
    assert len([e for e in log.read() if e.get("executionAction") == "skip"]) == 1
    assert not updated.pendingTickets
    assert updated.ticketedDecisionIds == [ticket.decisionId]


def test_sell_at_gain_matches_broker_diluted_cost(setup):
    # 20 Nov: sold 84 of 218 IEF at 91.475 from cost 90.62; the broker then showed 134 at 90.084.
    entry, log, state, prereg = setup
    state.pendingTickets = []
    state.ticketedDecisionIds = []
    state.positions["AAA"] = dict(qty=50, avgCost=100, sleeve="satellite", kind="drift",
        stop=94, entryPrice=100, entryDate="2026-11-16", decisionId="prior:AAA")
    state.cash = 95000
    ticket = OrderTicket(**(entry.body() | dict(side="SELL", estFees=estimate_fees("SELL", 50))))
    state.reserve(ticket)
    preflight(fixture("accounts"), state, frozen_config(), prereg, prompt_version(), ["AAA"], log)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    record(tickets, [request | dict(status="placed", response=fixture("placement"))], log)
    history = fixture("history")
    history["data"]["orders"][0].update(side=2, cum_qty="20", avg_fill_price="110", status=2)
    positions = fixture("positions")
    positions["data"][0].update(qty=30, cost_price=round((50*100-20*110)/30, 3), text="prior:AAA")
    cash = dict(cash=95000+20*110-estimate_fees("SELL", 20),
                equity=95000+20*110-estimate_fees("SELL", 20)+30*100)
    history, positions, cash = parse_history(history), parse_positions(positions), parse_cash(cash)
    updated, result = reconcile(tickets, history, positions, cash, state, log)
    assert not result["halted"], result
    assert updated.positions["AAA"]["avgCost"] == pytest.approx((50*100-20*110)/30, abs=.001)
    assert updated.positions["AAA"]["entryPrice"] == 100


def _sell_setup(setup):
    entry, log, state, prereg = setup
    state.pendingTickets = []
    state.ticketedDecisionIds = []
    state.positions["AAA"] = dict(qty=50, avgCost=100, sleeve="satellite", kind="drift",
        stop=94, entryPrice=100, entryDate="2026-11-16", decisionId="prior:AAA")
    state.cash = 95000
    ticket = OrderTicket(**(entry.body() | dict(side="SELL", estFees=estimate_fees("SELL", 50))))
    state.reserve(ticket)
    preflight(fixture("accounts"), state, frozen_config(), prereg, prompt_version(), ["AAA"], log)
    tickets = {ticket.decisionId: ticket}
    request = prepare(tickets, log)["orders"][0]
    record(tickets, [request | dict(status="placed", response=fixture("placement"))], log)
    return tickets, ticket, log, state


def _sell_snapshot(order, held, cash_value, closed=False):
    history = fixture("history")
    history["data"]["orders"][0].update(side=2, **order)
    positions = fixture("positions")
    positions["data"][0].update(qty=held, text="prior:AAA")
    if closed:
        positions["data"][0].update(qty="0", cost_price="0", cur_price="0")
    cash = dict(cash=cash_value, equity=cash_value + held * 100)
    return parse_history(history), parse_positions(positions), parse_cash(cash)


def test_closed_zero_quantity_position_row_is_dropped():
    positions = fixture("positions")
    positions["data"].append(positions["data"][0] | dict(symbol="US.ZZZ", qty="0", cost_price="0", cur_price="0"))
    parsed = parse_positions(positions)
    assert [row["ticker"] for row in parsed] == ["AAA"]


def test_resting_partial_sell_listed_as_unfilled_shares_waits_then_completes(setup):
    tickets, ticket, log, state = _sell_setup(setup)
    # 20 of 50 sold at 100.6; the broker lists the order as 30 shares with cum_qty 0.
    history, positions, cash = _sell_snapshot(dict(qty="30", cum_qty="0", avg_fill_price="0", status=2),
                                              30, 95000 + 20 * 100.6)
    waiting, result = reconcile(tickets, history, positions, cash, state, log)
    assert not result["halted"] and not result["diff"] and result["inFlight"] == ["AAA"]
    assert waiting.positions["AAA"]["qty"] == 50 and waiting.cash == pytest.approx(95000)
    assert [p["qty"] for p in waiting.pendingTickets] == [50] and waiting.pendingTickets[0]["submitted"]
    proceeds = 50 * 100.5 - estimate_fees("SELL", 50)
    history, positions, cash = _sell_snapshot(dict(qty="50", cum_qty="50", avg_fill_price="100.5", status=4),
                                              0, 95000 + proceeds, closed=True)
    done, result = reconcile(tickets, history, positions, cash, waiting, log)
    assert not result["halted"] and "AAA" not in done.positions and not done.pendingTickets
    assert done.cash == pytest.approx(95000 + proceeds)


@pytest.mark.parametrize("held, cash_gain", [(25, 2012), (30, -5), (30, 20 * 100 * 1.2)])
def test_resting_partial_with_inconsistent_broker_state_halts(setup, held, cash_gain):
    tickets, ticket, log, state = _sell_setup(setup)
    history, positions, cash = _sell_snapshot(dict(qty="30", cum_qty="0", avg_fill_price="0", status=2),
                                              held, 95000 + cash_gain)
    updated, result = reconcile(tickets, history, positions, cash, state, log)
    assert updated.halted and result["diff"]


def test_qty_mismatch_outside_resting_partial_still_halts(setup):
    tickets, ticket, log, state = _sell_setup(setup)
    history, positions, cash = _sell_snapshot(dict(qty="30", cum_qty="0", avg_fill_price="0", status=4),
                                              30, 95000 + 2012)
    with pytest.raises(ValueError, match="order history mismatch: qty"):
        reconcile(tickets, history, positions, cash, state, log)
