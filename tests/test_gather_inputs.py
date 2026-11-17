"""Offline input contracts and a real phase-runner rehearsal; never call a broker."""

from argparse import Namespace
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from moowoo import config as C, data
from moowoo.events import canonical_bytes
from moowoo.ledger import EventLog, verify
from moowoo.portfolio import PortfolioState
from moowoo.tickets import OrderTicket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import convert_quotes
import gather_inputs
import run_session
from plan_session import atomic_json, load_bars, read_json

NOW = "2026-11-18T15:00:00Z"


@pytest.fixture
def provider(tmp_path, monkeypatch):
    """Exercise the real data adapter, replacing only its network provider."""
    calls = []
    class Provider:
        def history(self, **kwargs):
            calls.append(kwargs)
            dates = pd.bdate_range("2026-05-20", "2026-11-18")
            close = 100 + np.sin(np.arange(len(dates)))
            return pd.DataFrame(dict(Open=close-.1, High=close+1, Low=close-1,
                Close=close, Volume=np.full(len(dates), 100_000_000.)), index=dates)

        def get_earnings_dates(self, **kwargs):
            return pd.DataFrame(index=pd.DatetimeIndex([]))

    monkeypatch.setattr(data, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(data, "_provider", lambda symbol: Provider())
    monkeypatch.setattr(data.yf, "Ticker", lambda *a, **k: pytest.fail("unexpected network"))
    # Keep the provider tests small; the real preflight still verifies the full frozen universe.
    universe = dict(passing=["AAPL", "MSFT"], date="2026-11-16")
    universe["passingSha256"] = hashlib.sha256(canonical_bytes(universe["passing"])).hexdigest()
    source = tmp_path / "universe.json"
    atomic_json(source, universe)
    frozen = gather_inputs.frozen_config()
    frozen["universe"] = dict(file=str(source), passingSha256=universe["passingSha256"])
    monkeypatch.setattr(gather_inputs, "frozen_config", lambda: frozen)
    return calls


def workspace(tmp_path, kind="morning", state=None):
    root = tmp_path / "runtime"
    run_id = f"2026-11-18-{kind}-fixture"
    inputs = root / "inputs" / run_id
    inputs.mkdir(parents=True)
    atomic_json(root / ".session.json", dict(runId=run_id, kind=kind, phase="baseline",
                                            expiresAt="2026-11-18T15:45:00Z"))
    atomic_json(root / "state.json", (state or PortfolioState(cash=100000)).to_dict())
    return inputs


def raw_quotes(inputs, **changes):
    request = read_json(inputs / "quote-request.json")
    rows = [dict(code=code, last_price="100.00", bid_price="99.99", ask_price="100.01",
                 data_date="2026-11-18", data_time="10:00:00") | changes for code in request["codes"]]
    payload = dict(ret_code=0, ret_msg="success", data=dict(quotes=rows))
    atomic_json(inputs / "quotes-raw.json", payload)
    return payload


def broker_inputs(inputs):
    def envelope(data):
        return dict(ret_code=0, ret_msg="success", data=data)
    payloads = dict(accounts=envelope(dict(accounts=[dict(account_id="synthetic-paper-account",
        market_id=100, account_type=2, account_title="Qoder paper rehearsal")])),
        history=envelope(dict(orders=[], pagination=dict(has_more=False, next_key="0"))),
        positions=envelope(dict(positions=[])),
        cash=envelope(dict(balance="100000.00", total_asset="100000.00", hold="0.00")))
    for name, payload in payloads.items():
        atomic_json(inputs / f"{name}.json", payload)


def test_completed_bars_and_minimal_morning_request(tmp_path, provider):
    inputs = workspace(tmp_path)
    result = gather_inputs.gather(inputs, "morning", NOW)
    assert result["barsAsOf"] == "2026-11-17"
    bars, errors = load_bars(inputs / "bars.json", "2026-11-17")
    assert not errors
    assert set(C.CORE_ETFS) | {C.REGIME_BENCHMARK} <= bars.keys()
    assert all(frame.index[-1] == pd.Timestamp("2026-11-17") for frame in bars.values())
    assert all(call["end"] == "2026-11-18" and not call["auto_adjust"] for call in provider)
    assert read_json(inputs / "candidates.json") == []
    assert read_json(inputs / "quote-request.json")["codes"] == sorted("US." + x for x in C.CORE_ETFS)
    assert not (inputs / "ratings.json").exists()
    assert not (inputs / "quotes.json").exists()
    raw_quotes(inputs)
    assert convert_quotes.convert(inputs, NOW)["quotes"] == len(C.CORE_ETFS)
    snapshot = read_json(inputs / "quotes.json")
    assert snapshot["now"] == NOW
    assert all(q["ts"] == NOW and q["bid"] == 99.99 for q in snapshot["quotes"].values())
    with pytest.raises(ValueError, match="already gathered"):
        gather_inputs.gather(inputs, "morning", NOW)


def test_ranked_debate_candidates_use_screen_identity(tmp_path, provider, monkeypatch):
    original = data.get_daily_bars
    def spike(symbols, start, end):
        frames = original(symbols, start, end)
        symbol = next(x for x in symbols if x not in {*C.CORE_ETFS, C.REGIME_BENCHMARK})
        # Nonzero stock-specific residual variance before the outlier move.
        for column in ("open", "high", "low", "close"):
            frames[symbol][column] += .3 * np.sin(np.arange(len(frames[symbol])) * .7)
        frames[symbol].iloc[-1] = [115, 117, 114, 116, 200_000_000]
        return frames
    monkeypatch.setattr(data, "get_daily_bars", spike)
    inputs = workspace(tmp_path)
    gather_inputs.gather(inputs, "morning", NOW)
    candidates = read_json(inputs / "candidates.json")
    screen = read_json(inputs / "screen.json")
    assert candidates and [row["ticker"] for row in candidates] == screen["picked"]
    for row in candidates:
        assert row["decisionId"] == f"{inputs.name}:{row['ticker']}"
        assert row["newsCutoff"] == ("2026-11-17T14:30:00Z" if row["moveKind"] == "gap" else "2026-11-17T21:00:00Z")
        assert row["primaryAgent"] == "manager" and row["quickSecondOpinionRequired"]
        assert 0 <= row["setupScore"] <= 5 and row["promptVersion"]
    events = EventLog(inputs.parent.parent / f"logs/{inputs.name}.jsonl", runId=inputs.name).read()
    assert len(events) == 1 and events[0]["type"] == "screen"


def test_watch_gathers_only_portfolio_without_screen(tmp_path, provider):
    state = PortfolioState(cash=99000, positions={"AAPL": dict(qty=10, avgCost=100,
        sleeve="satellite", kind="drift", entryPrice=100, entryDate="2026-11-17", signalAtr=2, stop=94)})
    inputs = workspace(tmp_path, "watch", state)
    gather_inputs.gather(inputs, "watch", NOW)
    assert set(read_json(inputs / "bars.json")) == {"AAPL"}
    assert read_json(inputs / "quote-request.json")["codes"] == ["US.AAPL"]
    assert not (inputs / "screen.json").exists()
    assert not (inputs / "ratings.json").exists()


@pytest.mark.parametrize("change", [dict(data_time="09:58:59"), dict(data_time="10:00:01"),
    dict(bid_price="nan"), dict(ask_price="0"), dict(bid_price="101"), dict(last_price=True)])
def test_quote_refusal_removes_old_snapshot(tmp_path, provider, change):
    inputs = workspace(tmp_path)
    gather_inputs.gather(inputs, "morning", NOW)
    raw_quotes(inputs)
    convert_quotes.convert(inputs, NOW)
    raw_quotes(inputs, **change)
    with pytest.raises(ValueError):
        convert_quotes.convert(inputs, NOW)
    assert not (inputs / "quotes.json").exists()


@pytest.mark.parametrize("damage", ["missing", "duplicate", "failed", "naive", "missing_bid"])
def test_quote_envelope_failures(tmp_path, provider, damage):
    inputs = workspace(tmp_path)
    gather_inputs.gather(inputs, "morning", NOW)
    payload = raw_quotes(inputs)
    rows = payload["data"]["quotes"]
    if damage == "missing":
        rows.pop()
    elif damage == "duplicate":
        rows.append(rows[0])
    elif damage == "failed":
        payload["ret_code"] = -1
    elif damage == "missing_bid":
        del rows[0]["bid_price"]
    else:
        del rows[0]["data_date"], rows[0]["data_time"]
        rows[0]["update_time"] = "2026-11-18T15:00:00"
    atomic_json(inputs / "quotes-raw.json", payload)
    with pytest.raises((ValueError, KeyError)):
        convert_quotes.convert(inputs, NOW)


def test_mcp_text_batch_and_aware_timestamp(tmp_path, provider):
    inputs = workspace(tmp_path)
    gather_inputs.gather(inputs, "morning", NOW)
    payload = raw_quotes(inputs)
    for row in payload["data"]["quotes"]:
        del row["data_date"], row["data_time"]
        row["update_time"] = "2026-11-18T10:00:00-05:00"
    atomic_json(inputs / "quotes-raw.json", [dict(content=[dict(type="text", text=json.dumps(payload))])])
    assert convert_quotes.convert(inputs, NOW)["converted"]


def test_snapshot_wall_time_and_gather_cli(tmp_path, provider, monkeypatch, capsys):
    inputs = workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gather_inputs.py", "--kind", "morning", "--inputs", str(inputs), "--now", NOW])
    gather_inputs.main()
    assert json.loads(capsys.readouterr().out)["gathered"]
    payload = raw_quotes(inputs)
    rows = payload["data"].pop("quotes")
    for row in rows:
        del row["data_date"], row["data_time"]
        row["update_time"] = "2026-11-18 10:00:00"
    payload["data"]["snapshots"] = rows
    atomic_json(inputs / "quotes-raw.json", payload)
    convert_quotes.convert(inputs, NOW)
    assert all(row["ts"] == NOW for row in read_json(inputs / "quotes.json")["quotes"].values())


@pytest.mark.parametrize("phase,now", [("start", NOW), ("baseline", "2026-11-18T15:45:00Z"),
                                    ("baseline", "2026-11-19T15:00:00Z")])
def test_gather_refuses_wrong_phase_or_expired_run(tmp_path, provider, phase, now):
    inputs = workspace(tmp_path)
    control = inputs.parent.parent / ".session.json"
    atomic_json(control, read_json(control) | dict(phase=phase))
    with pytest.raises(ValueError):
        gather_inputs.gather(inputs, "morning", now)
    assert not (inputs / "session.json").exists()


def test_missing_required_bars_refused(tmp_path, provider, monkeypatch):
    original = data.get_daily_bars
    def missing(*args):
        frames = original(*args)
        del frames[C.REGIME_BENCHMARK]
        return frames
    monkeypatch.setattr(data, "get_daily_bars", missing)
    inputs = workspace(tmp_path)
    with pytest.raises(ValueError, match="required portfolio/benchmark"):
        gather_inputs.gather(inputs, "morning", NOW)
    assert not (inputs / "session.json").exists()
    assert C.REGIME_BENCHMARK in read_json(inputs / "gather-report.json")["errors"]


@pytest.mark.parametrize("kind", ["morning", "watch"])
def test_no_order_rehearsal_real_runner(tmp_path, provider, monkeypatch, kind):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, check=True)
    # Only synthetic routing is used; no credentials, service or order calls.
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    args = Namespace(kind=kind, phase="start", dir=tmp_path / "runtime", remote=str(remote))
    started = run_session.run(args, NOW)
    inputs = Path(started["inputs"])
    atomic_json(Path(started["state"]), PortfolioState(cash=100000).to_dict())
    broker_inputs(inputs)
    for phase in ("preflight", "reconcile"):
        args.phase = phase
        result = run_session.run(args, NOW)
        assert not result.get("halted")
    assert result["phase"] == "baseline"
    gather_inputs.gather(inputs, kind, NOW)
    raw_quotes(inputs)
    # Converter uses its real CLI entry point; gather used the real yfinance adapter with a fake provider.
    converted = subprocess.run([sys.executable, "scripts/convert_quotes.py", "--inputs", str(inputs),
                               "--now", NOW], cwd=ROOT, capture_output=True, text=True)
    assert converted.returncode == 0, converted.stderr
    if kind == "morning":
        assert read_json(inputs / "candidates.json") == []
        atomic_json(inputs / "ratings.json", [])
    for phase in ("plan", "prepare"):
        args.phase = phase
        result = run_session.run(args, NOW)
        assert result["phase"] == phase
    manifest = read_json(Path(args.dir) / f"tickets/{started['runId']}.json")
    for ticket in manifest["tickets"]:
        OrderTicket(**ticket)
    if kind == "morning":
        assert manifest["tickets"] and result["orders"]
        assert all(order["tool"] == "sim_trade_input_order" for order in result["orders"])
    else:
        assert manifest["tickets"] == result["orders"] == []
    assert verify(started["log"]).ok
    events = EventLog(started["log"], runId=started["runId"]).read()
    assert not any(event["type"] in ("fill", "halt") for event in events)
    # Never dispatch prepared arguments. Preserve the rehearsal and release its local lease.
    args.phase = "abort"
    assert run_session.run(args, NOW)["unlocked"]


@pytest.mark.parametrize("kind", ["morning", "watch"])
def test_phase_cli_contract_without_git_transport(tmp_path, provider, monkeypatch, kind):
    """Test actual phase CLIs separately when Windows Git blocks the full rehearsal."""
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "synthetic-paper-account")
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    inputs = workspace(tmp_path, kind)
    root = inputs.parent.parent
    log = root / f"logs/{inputs.name}.jsonl"
    common = ["--state", root / "state.json", "--log", log]
    broker_inputs(inputs)
    run_session.invoke("preflight.py", *common, "--accounts", inputs / "accounts.json")
    reconciled = run_session.invoke("reconcile.py", *common, "--runtime", root,
        "--history", inputs / "history.json", "--positions", inputs / "positions.json", "--cash", inputs / "cash.json")
    assert not reconciled.get("halted")
    gather_inputs.gather(inputs, kind, NOW)
    raw_quotes(inputs)
    convert_quotes.convert(inputs, NOW)
    planning = [*common, "--quotes", inputs / "quotes.json", "--bars", inputs / "bars.json",
                "--bars-asof", read_json(inputs / "session.json")["barsAsOf"], "--tickets-dir", root / "tickets"]
    if kind == "morning":
        atomic_json(inputs / "ratings.json", [])
        run_session.invoke("plan_session.py", *planning, "--ratings", inputs / "ratings.json", "--run-id", inputs.name)
    else:
        run_session.invoke("watch.py", *planning)
    tickets = root / f"tickets/{inputs.name}.json"
    run_session.validate_dispatch(read_json(tickets), NOW)
    prepared = run_session.invoke("execute_tickets.py", "prepare", "--tickets", tickets, "--log", log)
    if kind == "morning":
        assert prepared["orders"]
        for ticket in read_json(tickets)["tickets"]:
            OrderTicket(**ticket)
    else:
        assert prepared["orders"] == []
    assert verify(log).ok
