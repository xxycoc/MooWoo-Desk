"""Fetch, trim, save and check completed audit bars in one command."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import _common
import pandas as pd
from moowoo import calendar, config, data
from moowoo.desk_data import daily_frame
from moowoo.input_files import InputFileError, read_input
from moowoo.outcomes import read_events
from moowoo.persistence import LedgerStore
from moowoo.runlock import require_owned
from plan_session import atomic_json
from persist_ledger import redact_error


def audit_context(inputs, now):
    inputs = Path(inputs).resolve()
    root = inputs.parent.parent
    context = read_input(root / ".session.json")
    if (context["kind"] != "audit" or context["phase"] != "reconcile"
            or inputs != root / "inputs" / context["runId"]):
        raise ValueError("audit inputs require this run's reconciled audit directory")
    now = calendar.local_time(now)
    day = now.date().isoformat()
    close = calendar.session_close(now)
    if (not calendar.is_trading_day(now) or close is None or now < close
            or context["runId"][:10] != day):
        raise ValueError("audit bars require this session's actual completed close")
    require_owned(LedgerStore(root), context["holder"], now)
    return inputs, root, context, day


def check(inputs):
    inputs = Path(inputs)
    session = read_input(inputs / "session.json")
    bars = read_input(inputs / "bars.json")
    if not isinstance(session, dict) or not isinstance(bars, dict):
        raise InputFileError("bars.json/session.json: expected objects")
    asof = session.get("barsAsOf")
    if asof != inputs.name[:10]:
        raise InputFileError("session.json: barsAsOf does not match audit session")
    for symbol, rows in bars.items():
        try:
            frame = daily_frame(rows)
            if frame.index[-1].date().isoformat() != asof:
                raise ValueError("no bar through actual close")
        except (ValueError, KeyError, TypeError) as exc:
            raise InputFileError(f"bars.json: {symbol}: invalid completed OHLCV") from exc
    return dict(valid=True, bars=len(bars), barsAsOf=asof)


def gather(inputs, now=None):
    injected = now
    now = now or datetime.now(timezone.utc)
    inputs, root, context, day = audit_context(inputs, now)
    state = read_input(root / "state.json")
    events = read_events(sorted((root / "logs").glob("*.jsonl")))
    symbols = set(state["positions"]) | set(config.CORE_ETFS) | {config.REGIME_BENCHMARK}
    symbols.update(t["ticker"] for t in state["pendingTickets"])
    symbols.update(e["ticker"] for e in events if not e["drill"] and e.get("ticker")
                   and e["type"] in ("rating", "fill", "order_intent", "order_submitted", "shadow"))
    fetched = data.get_daily_bars(sorted(symbols), pd.Timestamp(day) - pd.Timedelta(days=config.HISTORY_CALENDAR_DAYS), day)
    bars, missing = {}, {}
    for symbol in sorted(symbols):
        try:
            frame = daily_frame(fetched[symbol])
            frame = frame.loc[frame.index <= day]
            if frame.empty or frame.index[-1].date().isoformat() != day:
                raise ValueError("completed close not available")
            bars[symbol] = json.loads(frame.reset_index(names="date").assign(
                date=lambda x: x.date.dt.strftime("%Y-%m-%d")).to_json(orient="records"))
        except (KeyError, ValueError, TypeError):
            missing[symbol] = "completed daily bars unavailable"
    audit_context(inputs, injected or datetime.now(timezone.utc))
    atomic_json(inputs / "audit-input-report.json", dict(source="yfinance", requested=sorted(symbols), missing=missing, barsAsOf=day))
    atomic_json(inputs / "bars.json", bars)
    atomic_json(inputs / "session.json", dict(kind="audit", runId=context["runId"], barsAsOf=day,
                sessionDate=day, actualClose=calendar.utc_stamp(calendar.session_close(day))))
    return check(inputs) | dict(missing=missing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.inputs) if args.check else gather(args.inputs)))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps(dict(valid=False, reason=redact_error(exc))))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
