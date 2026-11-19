"""Save available close metrics and explicit gaps, even after an audit abort."""
import argparse
import json
import math
from pathlib import Path
import re
import _common
from moowoo import calendar
from moowoo.audit import build
from moowoo.input_files import read_input
from moowoo.outcomes import read_events
from plan_session import atomic_json
from persist_ledger import redact_error

SLACK_DASHBOARD = "https://moowoo-desk-p36f61ggjia.qoder.website"
LONG_NUMBER = re.compile(r"\d{7,}")
LINE_LIMIT = 119


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _points(value):
    return f"{value:.2f}%" if _number(value) else "n/a"


def _fraction(value):
    return f"{value * 100:.2f}%" if _number(value) else "n/a"


def _line(text):
    text = LONG_NUMBER.sub(lambda match: "***" + match.group()[-4:], text)
    return text if len(text) <= LINE_LIMIT else text[:LINE_LIMIT - 3] + "..."


def slack_summary(report, events, day):
    """Fixed close summary for the audit schedule sink; no paths, IDs or credentials."""
    day = str(day)
    today = [event for event in events
             if not event.get("drill") and calendar.local_time(event["ts"]).date().isoformat() == day]
    intents = {event.get("decisionId"): event.get("side") for event in today
               if event["type"] == "order_intent"}
    trades = []
    for event in sorted((event for event in today if event["type"] == "fill"),
                        key=lambda event: event["ts"]):
        qty = f"{event['filledQty']:g}" if _number(event.get("filledQty")) else "n/a"
        price = f"{event['avgPrice']:.4f}" if _number(event.get("avgPrice")) else "n/a"
        side = event.get("side") or intents.get(event.get("decisionId")) or "n/a"
        trades.append(f"{event.get('ticker') or 'n/a'} {side} {qty} @ {price}")
    vetoes = sum(event["type"] == "risk_verdict" and event.get("verdict") == "veto" for event in today)
    skips = sum(event.get("executionAction") == "skip" or event.get("skipped") is True
                for event in today)
    halts = {}
    for event in today:
        if event["type"] != "halt":
            continue
        reason = event.get("reason") if isinstance(event.get("reason"), str) else ""
        reason = reason.strip() or "unspecified"
        halts[reason] = halts.get(reason, 0) + 1
    missing = report.get("missing") if isinstance(report.get("missing"), dict) else {}
    partial = bool(missing) or report.get("complete") is False
    if partial:
        keys = list(missing)[:3]
        report_text = ("partial (missing: " + ", ".join(str(key) for key in keys) + ")"
                       if keys else "partial")
    else:
        report_text = "complete"
    equity = report.get("equity")
    lines = [
        f"MooWoo Desk close, {day} (paper)",
        "Equity " + (f"${equity:,.2f}" if _number(equity) else "$n/a") +
        f" | total {_points(report.get('pnlPct'))} | today {_points(report.get('dailyPnlPct'))}"
        f" | SPY since 17 Nov open {_fraction(report.get('spyOpenProxyReturn'))}",
        "Trades today: " + (", ".join(trades) if trades else "none"),
        f"Risk: {vetoes} vetoes, {skips} skips",
        "Halts today: " + (", ".join(f"{reason} ({count})" for reason, count in halts.items())
                           if halts else "none"),
        "Report: " + report_text,
        "Dashboard: " + SLACK_DASHBOARD,
    ]
    return "\n".join(_line(line) for line in lines)


def write(root, context, log, abort_reason=None):
    root = Path(root)
    inputs = root / "inputs" / context["runId"]
    inputs.mkdir(parents=True, exist_ok=True)
    day = context["runId"][:10]
    previous = [read_input(p) for p in (root / "reports").glob("*.json")]
    try:
        bars = read_input(inputs / "bars.json")
        session = read_input(inputs / "session.json")
        if not isinstance(session, dict) or session.get("barsAsOf") != day or not isinstance(bars, dict):
            raise ValueError("invalid audit bars/session metadata")
    except (ValueError, OSError):
        bars = {}
    events = []
    try:
        events = read_events(sorted((root / "logs").glob("*.jsonl")))
        report = build(read_input(root / "state.json"), events, bars, day, previous)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report = dict(sessionDate=day, complete=False, missing=dict(report=redact_error(exc)))
    if abort_reason:
        report["missing"]["auditAbort"] = abort_reason
        report["complete"] = False
        report["reconciliationVerified"] = False
    else:
        report["reconciliationVerified"] = True
    atomic_json(inputs / "report.json", report)
    destination = root / "reports" / f"{day}.json"
    if not abort_reason or not destination.exists() or not read_input(destination).get("reconciliationVerified"):
        atomic_json(destination, report)
    lines = [f"# MooWoo Desk close audit: {day}", "", "Partial report; unavailable values are not zero.", ""]
    for key in ("equity", "pnlPct", "dailyPnlPct", "brier", "creditsUsed", "orders", "vetoes", "skips", "spyOpenProxyReturn"):
        lines.append(f"- {key}: {report.get(key) if report.get(key) is not None else 'unavailable'}")
    if report.get("spyOpenProxyReturn") is not None:
        lines.extend(["", report["spyOpenProxyBasis"]])
    lines.extend(["", "Account metrics: " + json.dumps(report.get("accountMetrics", {})),
                  "Shadow mean excess: " + json.dumps(report.get("shadowMeanExcess", {})), "", "Missing:"])
    lines.extend(f"- {key}: {value}" for key, value in report["missing"].items())
    lines.extend(["", "Annualized ratios over this short window are descriptive and unstable.", "",
                  "1. What surprised me?", "2. What I would change?", "3. What the agents got right or wrong?"])
    (inputs / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    slack_text = slack_summary(report, events, day)
    (inputs / "slack.md").write_text(slack_text + "\n", encoding="utf-8", newline="\n")
    # The frozen daily_report schema requires all numeric fields. Preserve that contract.
    log.append("reflection_note", dict(prompt="Partial daily audit", text="Available metrics saved; see report.json/report.md",
        reportPath=f"inputs/{context['runId']}/report.json", missingFields=sorted(report["missing"]),
        dailyReportPartial=True, metrics={k: report.get(k) for k in ("equity", "pnlPct", "brier", "creditsUsed")}))
    if report["missing"]:
        log.append("halt", dict(scope="run", reason="Audit incomplete: " + ", ".join(sorted(report["missing"])),
                   disposition="report_only", missingFields=sorted(report["missing"])))
    return dict(report=str(inputs / "report.md"), partial=not report["complete"],
                slackPath=str(inputs / "slack.md"), slackText=slack_text)
