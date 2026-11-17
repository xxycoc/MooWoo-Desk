"""Phase runner around agent work. No model or broker calls; one durable lease."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

import _common  # noqa: F401
from moowoo import calendar, config
from moowoo.ledger import EventLog
from moowoo.persistence import LedgerError, LedgerStore, REMOTE
from moowoo.runlock import acquire, renew, require_owned
from moowoo.runtime_logs import existing_log, index_logs
from plan_session import atomic_json, read_json

ROOT = Path(__file__).resolve().parents[1]
PHASES = ("start", "preflight", "plan", "prepare", "record", "reconcile",
          "grade_calls", "score_hypotheses", "finish", "abort", "renew")


def validate_dispatch(manifest, now):
    if not calendar.is_regular_hours(now):
        raise ValueError("market closed before order handoff; no orders authorized")
    if calendar.minutes_since_open(now) < config.NO_ORDERS_FIRST_MINUTES:
        raise ValueError("no orders in first five minutes")
    for ticket in manifest["tickets"]:
        age = (calendar.local_time(now) - calendar.local_time(ticket["createdTs"])).total_seconds()
        if not 0 <= age <= config.STALE_PRICE_SECONDS:
            raise ValueError("ticket expired; abort and obtain fresh risk approval in a new run")
        if ticket["side"] == "BUY" and calendar.is_final_day(now):
            raise ValueError("no new entries on final day")


def invoke(script, *arguments):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)],
                            cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if result.returncode:
        from persist_ledger import redact_error
        if "--log" in arguments:
            log_path = Path(arguments[arguments.index("--log") + 1])
            atomic_json(log_path.parent.parent / f"receipts/commands/{uuid.uuid4().hex}.json",
                        dict(script=script, returncode=result.returncode,
                             stdout=redact_error(result.stdout), stderr=redact_error(result.stderr)))
        raise ValueError(f"{script} failed; inspect persisted logs; no further order work")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return dict(message=result.stdout.strip())


def run(args, now=None):
    injected_now = now
    now = calendar.local_time(now or datetime.now(timezone.utc))
    store = LedgerStore(args.dir, args.remote)
    root = store.directory
    control = root / ".session.json"
    if args.phase == "start":
        restored = store.restore()
        lock = acquire(store, args.kind, now)
        run_id = f"{now.date()}-{args.kind}-{uuid.uuid4().hex[:12]}"
        context = dict(kind=args.kind, runId=run_id, holder=lock["holder"], phase="start", expiresAt=lock["expiresAt"])
        atomic_json(control, context)
        log = EventLog(root / f"logs/{run_id}.jsonl", runId=run_id)
        skipped = calendar.skip(log, now, args.kind)
        if skipped:
            saved = store.save("Calendar skip", lock["holder"])
            control.unlink()
            return restored | skipped | saved
        inputs = root / "inputs" / run_id
        inputs.mkdir(parents=True, exist_ok=True)
        log.append("reflection_note", dict(prompt="Session runner", text=f"Started {args.kind} phase runner"), ts=calendar.utc_stamp(now))
        store.save("Start session", lock["holder"], release=False)
        return context | dict(inputs=str(inputs), state=str(root / "state.json"), log=str(log.path))

    context = read_json(control)
    if context["kind"] != args.kind:
        raise ValueError("kind differs from the acquired run")
    holder, run_id = context["holder"], context["runId"]
    if args.phase == "renew":
        lock = renew(store, holder, injected_now)
        context["expiresAt"] = lock["expiresAt"]
        atomic_json(control, context)
        return context | dict(renewed=True)
    log = EventLog(root / f"logs/{run_id}.jsonl", runId=run_id)
    if args.phase == "abort":
        log.append("reflection_note", dict(prompt="Session runner", text="Session aborted; retained all evidence", skipped=True))
        saved = store.save("Abort session; preserve evidence", holder)
        control.unlink()
        return saved
    require_owned(store, holder, injected_now)
    # Recording a receipt and persisting evidence remain mandatory if the clock crosses close.
    if args.phase not in ("record", "reconcile", "grade_calls", "score_hypotheses", "finish"):
        skipped = calendar.skip(log, now, args.kind)
        if skipped:
            saved = store.save("Calendar skip during session", holder)
            control.unlink()
            return skipped | saved
    previous = context["phase"]
    allowed = {"preflight": {"start"}, "plan": {"baseline"}, "prepare": {"plan"},
               "record": {"prepare", "record"}, "reconcile": {"preflight", "record", "reconcile"},
               "finish": {"reconcile"}}
    if args.kind == "audit":
        allowed = {"reconcile": {"start", "reconcile"}, "grade_calls": {"reconcile"},
                   "score_hypotheses": {"grade_calls"}, "finish": {"score_hypotheses"}}
    if previous not in allowed.get(args.phase, set()):
        raise ValueError(f"phase {args.phase} is not allowed after {previous} for {args.kind}")
    inputs = root / "inputs" / run_id
    state, tickets = root / "state.json", root / f"tickets/{run_id}.json"
    common = ["--state", state, "--log", log.path]
    result = {}
    next_phase = args.phase
    if args.phase == "preflight":
        result = invoke("preflight.py", *common, "--accounts", inputs / "accounts.json")
    elif args.phase == "plan":
        snapshot = read_json(inputs / "quotes.json")
        age = (now - calendar.local_time(snapshot["now"])).total_seconds()
        if not 0 <= age <= config.STALE_PRICE_SECONDS:
            raise ValueError("quote snapshot is not current; refresh before planning")
        metadata = read_json(inputs / "session.json")
        planning = [*common, "--quotes", inputs / "quotes.json", "--bars", inputs / "bars.json",
                    "--bars-asof", metadata["barsAsOf"], "--tickets-dir", root / "tickets"]
        if args.kind == "morning":
            result = invoke("plan_session.py", *planning, "--ratings", inputs / "ratings.json", "--run-id", run_id)
        else:
            result = invoke("watch.py", *planning)
    elif args.phase == "prepare":
        if calendar.minutes_since_open(now) < config.NO_ORDERS_FIRST_MINUTES:
            log.append("reflection_note", dict(prompt="Execution calendar", text="No orders in first five minutes", skipped=True))
            saved = store.save("First-five-minute skip", holder)
            control.unlink()
            return saved | dict(skipped=True, orders=[], reason="first five minutes; refresh plan in a new run")
        manifest = read_json(tickets)
        validate_dispatch(manifest, now)
        result = invoke("execute_tickets.py", "prepare", "--tickets", tickets, "--log", log.path)
    elif args.phase == "record":
        result = invoke("execute_tickets.py", "record", "--tickets", tickets, "--log", log.path,
                        "--responses", inputs / "responses.json")
    elif args.phase == "reconcile":
        command = [*common, "--runtime", root, "--history", inputs / "history.json",
                   "--positions", inputs / "positions.json", "--cash", inputs / "cash.json"]
        if (inputs / "history-pages.json").exists():
            command += ["--history-pages", inputs / "history-pages.json"]
        result = invoke("reconcile.py", *command)
        if previous == "preflight":
            next_phase = "baseline"
    elif args.phase == "grade_calls":
        metadata = read_json(inputs / "session.json")
        if metadata["barsAsOf"] != run_id[:10]:
            raise ValueError("audit requires completed bars through this session close")
        grade_log = root / f"logs/{run_id}-grading.jsonl"
        result["grading"] = invoke("grade_calls.py", "--logs", root / "logs/*.jsonl",
                                   "--bars", inputs / "bars.json", "--bars-asof", metadata["barsAsOf"], "--log", grade_log)
    elif args.phase == "score_hypotheses":
        result["hypotheses"] = invoke("score_hypotheses.py", "--logs", root / "logs/*.jsonl",
                                       "--out", root / "hypotheses/latest.json")
    elif args.phase == "finish":
        summaries = {}
        logs = index_logs(existing_log(source) for source in sorted((root / "logs").glob("*.jsonl")))
        for source_log in logs.values():
            source = source_log.path
            events = source_log.read()
            summaries[source.relative_to(root).as_posix()] = dict(count=len(events), hash=events[-1]["hash"] if events else None)
        atomic_json(root / f"handoffs/{run_id}.json", dict(runId=run_id, kind=args.kind, logs=summaries,
                    tickets=[p.relative_to(root).as_posix() for p in sorted((root / "tickets").glob("*.json"))], inputs=inputs.relative_to(root).as_posix()))
        result.update(store.save(f"Finish {args.kind} session", holder))
        control.unlink()
        return result
    if result.get("skipped") is True:
        saved = store.save("Skipped deterministic phase", holder)
        control.unlink()
        return result | saved
    context["phase"] = next_phase
    atomic_json(root / f"receipts/{run_id}/{args.phase}-{uuid.uuid4().hex}.json", result)
    # Persist prepared attempts before handing exact arguments to the executor.
    store.save(f"Checkpoint {args.kind} {args.phase}", holder, release=False)
    require_owned(store, holder, injected_now)
    if args.phase == "prepare":
        # Git transport may cross the close or ticket freshness limit while saving.
        validate_dispatch(manifest, injected_now or datetime.now(timezone.utc))
    atomic_json(control, context)
    # Phase scripts may echo runId; the runner's own value is authoritative.
    return {**result, "phase": next_phase, "runId": run_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("morning", "watch", "audit"))
    parser.add_argument("--phase", choices=PHASES, default="start")
    parser.add_argument("--dir", default="runtime")
    parser.add_argument("--remote", default=REMOTE)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args)))
        return 0
    except (ValueError, KeyError, TypeError, OSError, LedgerError) as exc:
        # Ledger errors are deliberately free of git output; no broker payloads are echoed.
        from persist_ledger import redact_error
        recovery = "local copy retained; run --phase abort to persist evidence when ownership permits"
        if args.phase != "renew" and not isinstance(exc, LedgerError):
            try:
                args.phase = "abort"
                run(args)
                recovery = "failure evidence saved and lock released"
            except (ValueError, KeyError, TypeError, OSError, LedgerError):
                pass
        print(json.dumps(dict(halted=True, reason=redact_error(exc), recovery=recovery)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
