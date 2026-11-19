"""Save available close metrics and explicit gaps, even after an audit abort."""
import argparse
import json
from pathlib import Path
import _common
from moowoo.audit import build
from moowoo.input_files import read_input
from moowoo.outcomes import read_events
from plan_session import atomic_json
from persist_ledger import redact_error


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
    try:
        report = build(read_input(root / "state.json"), read_events(sorted((root / "logs").glob("*.jsonl"))), bars, day, previous)
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
    # The frozen daily_report schema requires all numeric fields. Preserve that contract.
    log.append("reflection_note", dict(prompt="Partial daily audit", text="Available metrics saved; see report.json/report.md",
        reportPath=f"inputs/{context['runId']}/report.json", missingFields=sorted(report["missing"]),
        dailyReportPartial=True, metrics={k: report.get(k) for k in ("equity", "pnlPct", "brier", "creditsUsed")}))
    if report["missing"]:
        log.append("halt", dict(scope="run", reason="Audit incomplete: " + ", ".join(sorted(report["missing"])),
                   disposition="report_only", missingFields=sorted(report["missing"])))
    return dict(report=str(inputs / "report.md"), partial=not report["complete"])
