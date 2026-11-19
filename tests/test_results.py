"""Results builder: missing days, privacy masking, snapshot choice and outputs."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moowoo.ledger import EventLog
import build_results


def add_run(ledger, run_id, ts, total_asset):
    inputs = ledger / "inputs" / run_id
    inputs.mkdir(parents=True)
    (inputs / "cash.json").write_text(json.dumps({
        "code": 0,
        "data": {"total_asset": total_asset, "account_id": "987654321",
                 "token": "secret-token"},
    }), encoding="utf-8")
    log = EventLog(ledger / "logs" / f"{run_id}.jsonl", runId=run_id)
    log.append("run_started", dict(universe=["IEF", "XLP"], equity=100000, cash=100000,
                                   tier="normal", configHash="a" * 64, promptVersion="test-v0",
                                   trdEnv="SIMULATE"), ts=ts)
    return log


def ledger_three_days(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "logs").mkdir(parents=True)
    (ledger / "reports").mkdir()
    (ledger / "reports" / "2026-11-17.json").write_text(json.dumps(
        {"equity": 100250, "reconciliationVerified": True}), encoding="utf-8")
    add_run(ledger, "2026-11-19-morning-aaaaaa", "2026-11-19T15:00:00Z", "100500.00")
    log = add_run(ledger, "2026-11-19-watch-bbbbbb", "2026-11-19T20:00:00Z", "100900.00")
    intent = dict(sleeve="core", qty=10, limitPrice=98, notional=980, stop=95,
                  sizing={"method": "fixed_risk", "riskBudget": 50})
    log.append("order_intent", intent | dict(ticker="IEF", side="BUY"),
               ts="2026-11-19T20:01:00Z")
    log.append("order_submitted", dict(ticker="IEF", orderId="SIM-9876543210", qty=10,
                                       limitPrice=98, trdEnv="SIMULATE"),
               ts="2026-11-19T20:02:00Z")
    log.append("fill", dict(ticker="IEF", orderId="SIM-9876543210", status="FILLED",
                            filledQty=10, avgPrice=98.5, source="order_status", fees=0.99),
               ts="2026-11-19T20:03:00Z")
    log.append("order_intent", intent | dict(ticker="XLP", side="SELL"),
               ts="2026-11-19T20:04:00Z")
    log.append("order_submitted", dict(ticker="XLP", orderId="SIM-1122334455", qty=5,
                                       limitPrice=91, trdEnv="SIMULATE"),
               ts="2026-11-19T20:05:00Z")
    log.append("fill", dict(ticker="XLP", orderId="SIM-1122334455", status="FILLED",
                            filledQty=5, avgPrice=91.6, source="order_status", fees=0.5),
               ts="2026-11-19T20:06:00Z")
    log.append("risk_verdict", dict(ticker="ACM", verdict="veto", rules=["correlation"],
                                    firedRule="correlation", qtyAfter=0),
               ts="2026-11-19T20:07:00Z")
    log.append("halt", dict(reason="broker order 1234567890 unmatched", scope="run"),
               ts="2026-11-19T20:08:00Z")
    return ledger


def test_missing_day_snapshot_choice_and_masking(tmp_path):
    ledger = ledger_three_days(tmp_path)
    out = tmp_path / "docs"
    results = build_results.build(ledger, out)
    assert (out / "results.json").is_file()
    assert (out / "results.md").is_file()

    days = {row["day"]: row for row in results["days"]}
    assert list(days) == ["2026-11-17", "2026-11-18", "2026-11-19"]
    assert days["2026-11-17"]["equity"] == 100250
    assert days["2026-11-17"]["source"] == "audit report"
    assert days["2026-11-18"] == {"day": "2026-11-18", "equity": None, "source": "missing"}
    assert days["2026-11-19"]["equity"] == 100900
    assert days["2026-11-19"]["source"] == "last broker snapshot 15:00 ET"
    assert results["missingDays"] == ["2026-11-18"]
    assert all(value is None for value in results["metrics"].values())
    assert results["dailyMean"]["interval95"] is None

    trades = results["trades"]
    assert [(row["ticker"], row["side"], row["filledQty"]) for row in trades] == [
        ("IEF", "BUY", 10), ("XLP", "SELL", 5)]
    assert trades[0]["avgPrice"] == 98.5 and trades[0]["fees"] == 0.99
    assert trades[0]["status"] == "FILLED"
    assert results["counts"]["vetoes"] == {"correlation": 1}

    text = (out / "results.md").read_text(encoding="utf-8")
    payload = json.dumps(results) + text
    assert "9876543210" not in payload and "SIM-***3210" in payload
    assert "1122334455" not in payload and "SIM-***4455" in payload
    assert "987654321" not in payload
    assert "secret-token" not in payload
    assert "1234567890" not in payload and "broker order ***7890 unmatched" in payload
    assert "unavailable" in text and "2026-11-18" in text
    assert "None" not in json.dumps(results) and "nan" not in json.dumps(results)


def test_complete_series_metrics_bootstrap_and_spy(tmp_path):
    ledger = tmp_path / "ledger"
    (ledger / "logs").mkdir(parents=True)
    (ledger / "reports").mkdir()
    for day, equity in (("2026-11-17", 100000), ("2026-11-18", 99500),
                        ("2026-11-19", 100900)):
        (ledger / "reports" / f"{day}.json").write_text(json.dumps(
            {"equity": equity, "reconciliationVerified": True}), encoding="utf-8")
    bars = ledger / "inputs" / "bars-run"
    bars.mkdir(parents=True)
    (bars / "bars.json").write_text(json.dumps({"SPY": [
        {"date": "2026-11-17", "open": 400.0, "close": 404.0},
        {"date": "2026-11-18", "open": 404.0, "close": 405.0},
        {"date": "2026-11-19", "open": 405.0, "close": 406.0},
    ]}), encoding="utf-8")
    out = tmp_path / "docs"
    completed = subprocess.run(
        [sys.executable, str(Path(build_results.__file__)),
         "--ledger", str(ledger), "--out", str(out)],
        capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert results["missingDays"] == []
    assert results["metricsUnavailableReason"] is None
    assert results["metrics"]["totalReturn"] == pytest.approx(0.009)
    assert results["metrics"]["maxDrawdown"] == pytest.approx(-0.005)
    assert results["dailyMean"]["resamples"] == 10000
    assert results["dailyMean"]["seed"] == 7
    low, high = results["dailyMean"]["interval95"]
    assert low <= results["dailyMean"]["mean"] <= high
    assert results["spy"]["returnPct"] == pytest.approx(0.015)
    assert results["spy"]["end"] == "2026-11-19 close"
    text = (out / "results.md").read_text(encoding="utf-8")
    assert "Annualised ratios over about eight sessions are unstable" in text
