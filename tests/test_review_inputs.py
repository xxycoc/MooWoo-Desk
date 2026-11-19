"""Regression coverage for transport failures versus genuine broker disagreements."""
from argparse import Namespace
import json
import subprocess
import sys

import pytest

from _execution import command
from check_broker_input import save
from moowoo.input_files import InputFileError
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from plan_session import atomic_json, frozen_config
import reconcile as cli
from test_execution import fixture
from test_runtime_guards import prepared, NOW, RUN
import dispatch_check
from datetime import timedelta


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    state = tmp_path / "state.json"
    atomic_json(state, PortfolioState(cash=100000).to_dict())
    log = EventLog(tmp_path / "run.jsonl", runId="run")
    atomic_json(tmp_path / "tickets.json", dict(runId="run", configHash=frozen_config()["configHash"], tickets=[]))
    atomic_json(tmp_path / "history.json", dict(ret_code=0, ret_msg="ok", data=dict(orders=[]), pagination=dict(has_more=False, next_key="")))
    atomic_json(tmp_path / "positions.json", dict(ret_code=0, ret_msg="ok", data=dict(positions=[])))
    atomic_json(tmp_path / "cash.json", dict(ret_code=0, ret_msg="ok", data=dict(balance=100000, total_asset=100000, hold=0)))
    args = Namespace(**{key: str(tmp_path / (key + ".json")) for key in ("state", "tickets", "history", "positions", "cash")}, log=str(log.path))
    return args, log


@pytest.mark.parametrize("bad", ["missing", "json", "shape", "field"])
def test_input_abort_does_not_poison_next_run(baseline, bad):
    args, log = baseline
    from pathlib import Path
    path = Path(args.cash)
    original = path.read_bytes()
    if bad == "missing": path.unlink()
    elif bad == "json": path.write_text("{")
    elif bad == "shape": path.write_text("[]")
    else: atomic_json(path, dict(ret_code=0, ret_msg="ok", data=dict(balance=100000, total_asset=100000)))
    assert command(args, cli.run, persist_halt=True) == 2
    assert not json.loads(Path(args.state).read_text())["halted"]
    assert "cash.json" in log.read()[-1]["reason"]
    path.write_bytes(original)
    args.log = str(path.parent / "next.jsonl")
    atomic_json(args.tickets, dict(runId="next", configHash=frozen_config()["configHash"], tickets=[]))
    assert command(args, cli.run, persist_halt=True) == 0


@pytest.mark.parametrize("bad", ["account", "equity", "cash", "identity", "history"])
def test_disagreements_still_persist_halt(baseline, bad):
    args, log = baseline
    from pathlib import Path
    cash = json.loads(Path(args.cash).read_text())
    if bad == "account": cash["data"]["acc_id"] = "wrong"
    if bad == "equity": cash["data"]["total_asset"] += 100
    if bad == "cash":
        cash["data"]["balance"] += 100
        cash["data"]["total_asset"] += 100
    atomic_json(args.cash, cash)
    if bad == "identity":
        atomic_json(args.positions, dict(ret_code=0, ret_msg="ok", data=dict(positions=[dict(symbol="IEF", qty=1, cost_price=100, cur_price=100)])))
    if bad == "history":
        row = fixture("history")
        row["data"]["orders"][0]["cum_qty"] = "100"
        atomic_json(args.history, row)
    assert command(args, cli.run, persist_halt=True) == 2
    assert json.loads(Path(args.state).read_text())["halted"]
    assert log.read()[-1]["type"] == "halt"


def test_save_trims_checks_and_caps_retries(tmp_path, monkeypatch):
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    path = tmp_path / "positions.json"
    raw = dict(ret_code=0, ret_msg="ok", data=dict(positions=[dict(symbol="IEF", qty=1, cost_price=100, cur_price=100, unused="discard")]))
    assert save(path, "positions", json.dumps(raw))["valid"]
    assert "unused" not in path.read_text()
    del raw["data"]["positions"][0]["qty"]
    for remaining in (2, 1, 0):
        with pytest.raises(InputFileError, match=f"qty.*retries left {remaining}"):
            save(path, "positions", json.dumps(raw))
        assert not path.exists()
    with pytest.raises(InputFileError, match="exhausted"):
        save(path, "positions", "{}")


def test_stale_refresh_once_without_new_order_attempt(prepared):
    args, ticket, log, order, lock = prepared
    stale = NOW + timedelta(seconds=61)
    assert dispatch_check.run(args, stale)["retryable"]
    path = args.dir / f"inputs/{RUN}/quotes-raw-AAA.json"
    raw = json.loads(path.read_text())
    raw["data"]["snapshot_list"][0]["update_time"] = stale.isoformat()
    atomic_json(path, raw)
    assert dispatch_check.run(args, stale)["attempt"] == 1
    with pytest.raises(ValueError, match="resolved"):
        dispatch_check.run(args, stale)


def test_save_actual_cli_reports_missing_file(tmp_path):
    result = subprocess.run([sys.executable, "scripts/check_broker_input.py", "--kind", "cash", "--file", str(tmp_path / "cash.json")], capture_output=True, text=True)
    assert result.returncode == 2
    assert "cash.json" in result.stdout and "missing input file" in result.stdout
