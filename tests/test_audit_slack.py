"""The audit's code-written Slack close summary and its schedule delivery."""

from argparse import Namespace
import json
from pathlib import Path
import subprocess
import sys

from audit_report import SLACK_DASHBOARD, slack_summary, write
from test_review_audit_core import audit_workspace
import run_session

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-19"
NOW = "2026-11-19T21:00:00Z"


def report(**overrides):
    base = dict(sessionDate=DAY, equity=101234.56, pnlPct=1.23, dailyPnlPct=-0.45,
                spyOpenProxyReturn=0.0123, complete=True, missing={})
    base.update(overrides)
    return base


def event(kind, ts=NOW, **payload):
    return dict(type=kind, ts=ts, drill=False, **payload)


def test_full_report_summary_is_fixed_and_short():
    text = slack_summary(report(), [], DAY)
    lines = text.splitlines()
    assert lines == [
        "MooWoo Desk close, 2026-11-19 (paper)",
        "Equity $101,234.56 | total 1.23% | today -0.45% | SPY since 17 Nov open 1.23%",
        "Trades today: none",
        "Risk: 0 vetoes, 0 skips",
        "Halts today: none",
        "Report: complete",
        "Dashboard: " + SLACK_DASHBOARD,
    ]
    assert len(lines) <= 8 and all(len(line) < 120 for line in lines)


def test_partial_report_never_reports_missing_values_as_zero():
    partial = report(equity=None, pnlPct=None, dailyPnlPct=None, spyOpenProxyReturn=None,
                     complete=False,
                     missing={"accountDailySeries": "no daily series", "brier": "no matured outcomes",
                              "creditsUsed": "no ratings measured", "spyOpenProxyReturn": "no close"})
    lines = slack_summary(partial, [], DAY).splitlines()
    assert lines[1] == "Equity $n/a | total n/a | today n/a | SPY since 17 Nov open n/a"
    assert lines[5] == "Report: partial (missing: accountDailySeries, brier, creditsUsed)"
    assert "$0" not in lines[1]


def test_two_fills_one_halt_and_side_from_intents():
    events = [
        event("order_intent", ticker="XLV", side="BUY", decisionId="2026-11-19-watch-abc:XLV"),
        event("order_intent", ticker="IEF", side="SELL", decisionId="2026-11-19-watch-abc:IEF"),
        event("fill", ts="2026-11-19T20:59:00Z", ticker="IEF", filledQty=100, avgPrice=95.25,
              decisionId="2026-11-19-watch-abc:IEF"),
        event("fill", ticker="XLV", filledQty=50, avgPrice=100.5, decisionId="2026-11-19-watch-abc:XLV"),
        event("halt", reason="missing required broker field: qty", scope="run"),
        event("order_intent", ts="2026-11-18T21:00:00Z", ticker="GLD", side="BUY",
              decisionId="2026-11-18-watch-abc:GLD"),
    ]
    lines = slack_summary(report(), events, DAY).splitlines()
    assert lines[2] == "Trades today: IEF SELL 100 @ 95.2500, XLV BUY 50 @ 100.5000"
    assert lines[4] == "Halts today: missing required broker field: qty (1)"


def test_long_numbers_and_lines_are_masked_and_capped():
    reason = "missing broker row for order 123456789 and " + "x" * 200
    text = slack_summary(report(), [event("halt", reason=reason)], DAY)
    halt = text.splitlines()[4]
    assert "123456789" not in text and "***6789" in halt
    assert len(halt) < 120 and halt.endswith("...")


def test_write_saves_slack_md_with_partial_summary(tmp_path):
    root, inputs, context, log = audit_workspace(tmp_path)
    result = write(root, context, log)
    path = inputs / "slack.md"
    assert Path(result["slackPath"]) == path
    assert path.read_text(encoding="utf-8") == result["slackText"] + "\n"
    assert result["partial"]
    assert "Report: partial (missing: brier, creditsUsed, shadow.llm)" in result["slackText"]
    assert result["slackText"].splitlines()[1].startswith("Equity $100,000.00")
    assert "SPY since 17 Nov open n/a" in result["slackText"]
    assert context["runId"] not in result["slackText"]


def test_abort_prints_summary_last_between_markers(tmp_path, monkeypatch, capsys):
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(run_session, "require_owned", lambda *a: None)
    monkeypatch.setattr(run_session.LedgerStore, "save", lambda *a, **k: dict(saved=True))
    monkeypatch.setattr(run_session, "publish_feed", lambda *a: False)
    monkeypatch.setattr(sys, "argv", ["run_session.py", "--kind", "audit", "--phase", "abort",
                                      "--dir", str(root), "--reason", "session.json: missing input file"])
    assert run_session.main() == 0
    out = capsys.readouterr().out.splitlines()
    start = out.index("SLACK SUMMARY START") + 1
    assert out[-1] == "SLACK SUMMARY END"
    assert out[start].startswith("MooWoo Desk close, 2026-11-18 (paper)")
    assert out[start + 5].startswith("Report: partial")
    assert json.loads(out[0])["slackText"] == "\n".join(out[start:-1])


def test_abort_result_carries_summary_for_the_sink(tmp_path, monkeypatch):
    root, inputs, context, log = audit_workspace(tmp_path)
    monkeypatch.setattr(run_session.LedgerStore, "save", lambda *a, **k: dict(saved=True))
    result = run_session.run(Namespace(kind="audit", phase="abort", dir=root, remote=run_session.REMOTE,
                                       reason="session.json: missing input file"), NOW)
    assert Path(result["slackPath"]) == inputs / "slack.md"
    assert result["slackText"] == (inputs / "slack.md").read_text(encoding="utf-8").rstrip("\n")


def deploy_bodies(settings):
    import qca_deploy
    return {op["key"]: op["body"] for op in qca_deploy.build_payloads(settings)["operations"]}


def test_only_audit_schedules_request_the_summary_reply():
    result = subprocess.run([sys.executable, "scripts/qca_deploy.py", "--stage", "schedules"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    bodies = {op["key"]: op["body"] for op in json.loads(result.stdout)["operations"]}
    audit_message = bodies["schedule.audit"]["initial_events"][0]["content"]
    assert ("end the session by replying with exactly the text between SLACK SUMMARY START "
            "and SLACK SUMMARY END, with nothing before or after it") in audit_message
    assert ("If no summary was printed, reply with one line: "
            "'MooWoo Desk audit <date>: no summary produced, see ledger.'") in audit_message
    for key in ("schedule.audit-early-close",):
        assert "SLACK SUMMARY END" in bodies[key]["initial_events"][0]["content"]
    for key in ("schedule.morning", "schedule.watcher-regular", "schedule.watcher-close",
                "schedule.watcher-early-close"):
        assert "SLACK SUMMARY" not in bodies[key]["initial_events"][0]["content"]
    paired = deploy_bodies({"moomoo_tool_names": ["quote_stock_quote"],
                            "SLACK_CHANNEL_PAIRING_ID": "pair_test"})
    assert paired["schedule.audit"]["sinks"] == [
        {"type": "im_channel", "channel_pairing_id": "pair_test"}]
    assert paired["schedule.audit-early-close"]["sinks"] == paired["schedule.audit"]["sinks"]
    assert paired["schedule.morning"]["sinks"] == []
