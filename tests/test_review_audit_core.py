"""Audit completeness, conditional core allocation and closing schedule regressions."""
from argparse import Namespace
from copy import deepcopy
import json
import subprocess
import sys

import pytest

from moowoo import calendar, config
from moowoo.audit import metrics, build
from moowoo.core import projected_core_state, require_core_fills
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.risk import check
from moowoo.tickets import OrderTicket
from plan_session import atomic_json, frozen_config
from test_risk_desk import desk, position
from test_gather_inputs import provider
import gather_audit_inputs
import audit_report
import run_session


def test_projected_core_budget_never_mutates_holdings(desk):
    proposal, state, market = desk
    state.cash = 70000
    state.positions["IEF"] = position("core", qty=300)
    sell = dict(decisionId="sell:IEF", ticker="IEF", side="SELL", sleeve="core", qty=200, limitPrice=100, estFees=1.03)
    buy = proposal | dict(ticker="XLV", sleeve="core", kind="core", qty=60)
    before = state.to_dict()
    assert check(buy, state, market)["verdict"] == "veto"
    projected, dependencies = projected_core_state(state, [sell])
    assert check(buy, projected, market)["verdict"] == "approve"
    assert dependencies == ["sell:IEF"] and state.to_dict() == before
    assert projected.cash == pytest.approx(89998.97)


@pytest.mark.parametrize("filled,blocked", [(0, True), (50, True), (100, False)])
def test_core_dispatch_needs_full_reconciled_fills(tmp_path, filled, blocked):
    state = PortfolioState(cash=80000, positions={"IEF": position("core", qty=100)}, sessionStartEquity=90000)
    ticket = OrderTicket(decisionId="run:XLV", ticker="XLV", side="BUY", qty=50,
        limitPrice=100, sleeve="core", kind="core", stop=0, reason="rebalance",
        configHash=frozen_config()["configHash"], createdTs="2026-11-19T15:00:00Z", estFees=.99)
    state.reserve(ticket)
    sell = ticket.to_dict() | dict(decisionId="run:IEF", ticker="IEF", side="SELL", qty=100)
    manifest = dict(tickets=[sell, ticket.to_dict()], coreSellDependencies={ticket.decisionId: ["run:IEF"]})
    log = EventLog(tmp_path / "run.jsonl", runId="run")
    log.append("order_submitted", dict(ticker="IEF", orderId="paper-order", qty=100, limitPrice=100, trdEnv="SIMULATE"), decisionId="run:IEF")
    state.execution = dict(fills={"paper-order": dict(filledQty=filled)})
    if blocked:
        with pytest.raises(ValueError, match="full reconciled"):
            require_core_fills(ticket, manifest, state, log, {"IEF": 100})
    else:
        require_core_fills(ticket, manifest, state, log, {"IEF": 100})
        state.positions["IEF"]["qty"] = 350
        with pytest.raises(ValueError, match="core target"):
            require_core_fills(ticket, manifest, state, log, {"IEF": 100})
        manifest["coreSellDependencies"] = {}
        with pytest.raises(ValueError, match="manifest mismatch"):
            require_core_fills(ticket, manifest, state, log, {"IEF": 100})


def test_plan_cli_reserves_conditional_buys_without_crediting_sells(desk, tmp_path):
    _, state, market = desk
    state.cash = 70000
    state.positions["IEF"] = position("core", qty=300, decisionId="old:IEF")
    payloads = dict(state=state.to_dict(), ratings=[],
        bars={symbol: [dict(date=str(day.date()), **row.to_dict()) for day, row in frame.iterrows()] for symbol, frame in market["bars"].items()},
        quotes=dict(now=market["now"], sessionDate=market["sessionDate"], quotes=market["quotes"]))
    for name, value in payloads.items(): atomic_json(tmp_path / f"{name}.json", value)
    command = [sys.executable, "scripts/plan_session.py", "--bars-asof", "2026-11-16", "--log", str(tmp_path / "plan.jsonl"), "--tickets-dir", str(tmp_path / "tickets")]
    for name in payloads: command += ["--" + name, str(tmp_path / f"{name}.json")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(next((tmp_path / "tickets").glob("*.json")).read_text())
    assert manifest["tickets"][0]["ticker"] == "IEF" and manifest["tickets"][0]["side"] == "SELL"
    buys = [t for t in manifest["tickets"] if t["side"] == "BUY"]
    assert {t["ticker"] for t in buys} == set(config.CORE_ETFS)-{"IEF"}
    assert all(manifest["coreSellDependencies"][t["decisionId"]] == [manifest["tickets"][0]["decisionId"]] for t in buys)
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["cash"] == 70000 and saved["positions"]["IEF"]["qty"] == 300
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(next((tmp_path / "tickets").glob("*.json")).read_text())["coreSellDependencies"] == manifest["coreSellDependencies"]


def audit_workspace(tmp_path):
    root = tmp_path / "runtime"
    run = "2026-11-18-audit-test"
    inputs = root / "inputs" / run
    inputs.mkdir(parents=True)
    context = dict(kind="audit", phase="reconcile", runId=run, holder="test")
    atomic_json(root / ".session.json", context)
    atomic_json(root / "state.json", PortfolioState(cash=100000).to_dict())
    log = EventLog(root / f"logs/{run}.jsonl", runId=run)
    log.append("reflection_note", dict(prompt="test", text="audit"))
    return root, inputs, context, log


def test_audit_fetch_save_check_real_adapter(provider, tmp_path, monkeypatch):
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(gather_audit_inputs, "require_owned", lambda *a: None)
    result = gather_audit_inputs.gather(inputs, "2026-11-18T21:10:00Z")
    assert result["valid"] and not result["missing"]
    assert set(json.loads((inputs / "bars.json").read_text())) == {*config.CORE_ETFS, "SPY"}
    assert json.loads((inputs / "session.json").read_text())["barsAsOf"] == "2026-11-18"
    assert gather_audit_inputs.check(inputs)["valid"]
    with pytest.raises(ValueError, match="completed close"):
        gather_audit_inputs.gather(inputs, "2026-11-18T20:59:00Z")
    result = audit_report.write(root, context, log)
    report = json.loads((inputs / "report.json").read_text())
    assert result["partial"] and report["equity"] == 100000
    assert report["brier"] is None and report["creditsUsed"] is None
    assert report["spyOpenProxyReturn"] is not None
    assert not json.loads((root / "state.json").read_text())["halted"]


def test_audit_abort_always_keeps_report_and_reason(tmp_path, monkeypatch):
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(run_session.LedgerStore, "save", lambda *a, **k: dict(saved=True))
    result = run_session.run(Namespace(kind="audit", phase="abort", dir=root, remote=run_session.REMOTE, reason="session.json: missing input file"), "2026-11-18T21:10:00Z")
    assert result["saved"]
    report = json.loads((inputs / "report.json").read_text())
    assert "session.json" in report["missing"]["auditAbort"]
    assert "session.json" in log.read()[-1]["text"]
    assert (inputs / "report.md").exists()
    assert not any(e["type"] == "daily_report" for e in log.read())


def test_metrics_zero_denominators_and_missing_close():
    assert metrics([100, 100, 100])["sharpe"] is None
    assert metrics([100, 102, 101])["sharpe"] is not None
    report = build(PortfolioState(cash=100000).to_dict(), [], {}, "2026-11-19")
    assert report["accountMetrics"]["sharpe"] is None
    assert "accountDailySeries" in report["missing"]


def test_close_schedules_real_cli_and_calendar():
    result = subprocess.run([sys.executable, "scripts/qca_deploy.py", "--stage", "schedules"], capture_output=True, text=True)
    assert result.returncode == 0
    ops = {op["key"]: op["body"] for op in json.loads(result.stdout)["operations"]}
    assert ops["schedule.watcher-close"]["trigger_policy"]["expression"] == "55 15 * * 1-5"
    assert ops["schedule.watcher-early-close"]["trigger_policy"]["expression"] == "55 12 27 11 *"
    assert calendar.run_allowed("watch", "2026-11-19T20:55:00Z")
    assert not calendar.run_allowed("watch", "2026-11-19T21:00:00Z")
    assert calendar.run_allowed("watch", "2026-11-27T17:55:00Z")
    assert not calendar.run_allowed("watch", "2026-11-27T18:00:00Z")
    assert not calendar.run_allowed("watch", "2026-11-27T20:55:00Z")


def test_audit_missing_session_main_logs_reason_and_saves_partial(tmp_path, monkeypatch, capsys):
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(run_session, "require_owned", lambda *a: None)
    monkeypatch.setattr(run_session.LedgerStore, "save", lambda *a, **k: dict(saved=True))
    monkeypatch.setattr(run_session, "publish_feed", lambda *a: False)
    monkeypatch.setattr(sys, "argv", ["run_session.py", "--kind", "audit", "--phase", "grade_calls", "--dir", str(root)])
    assert run_session.main() == 2
    assert "session.json" in capsys.readouterr().out
    assert any("session.json" in e.get("text", "") for e in log.read())
    assert (inputs / "report.md").exists()


def test_audit_missing_symbol_is_reported_not_fabricated(tmp_path, monkeypatch):
    from test_risk_desk import bars
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(gather_audit_inputs, "require_owned", lambda *a: None)
    monkeypatch.setattr(gather_audit_inputs.data, "get_daily_bars", lambda symbols, *a: {symbol: bars(end="2026-11-18") for symbol in symbols if symbol != "SPY"})
    result = gather_audit_inputs.gather(inputs, "2026-11-18T21:10:00Z")
    assert result["missing"] == {"SPY": "completed daily bars unavailable"}
    assert "SPY" not in json.loads((inputs / "bars.json").read_text())
    audit_report.write(root, context, log)
    report = json.loads((inputs / "report.json").read_text())
    assert report["spyOpenProxyReturn"] is None
    assert report["equity"] == 100000


def test_report_uses_matured_brier_and_contiguous_close_metrics(tmp_path):
    from test_outcomes import graded, bars
    source, rating, grades, outcome = graded(tmp_path)
    prior = [dict(sessionDate=day, equity=100000+i*100, reconciliationVerified=True)
             for i, day in enumerate(sorted(d.isoformat() for d in calendar.TRADING_DAYS if d.isoformat() < "2026-11-27"))]
    report = build(PortfolioState(cash=100800).to_dict(), source.read()+grades.read(), bars(), "2026-11-27", prior)
    assert report["brier"] == pytest.approx(.09)
    assert report["creditsUsed"] == 0  # This fixture explicitly measured zero.
    assert report["accountMetrics"]["sharpe"] is not None
    assert "brier" not in report["missing"] and "accountDailySeries" not in report["missing"]
