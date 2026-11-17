"""Gather completed market inputs after the runner's baseline reconciliation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import _common  # noqa: F401
import pandas as pd

from moowoo import calendar, config as C, data
from moowoo.desk_data import daily_frame
from moowoo.events import canonical_bytes
from moowoo.ledger import EventLog
from moowoo.portfolio import PortfolioState
from moowoo.screener import screen
from moowoo.setup_score import setup_score
from hash_prompts import prompt_version
from plan_session import ROOT, atomic_json, frozen_config, read_json
from session_info import info


def context(inputs, kind, now):
    inputs = Path(inputs).resolve()
    root = inputs.parent.parent
    control = read_json(root / ".session.json")
    if (inputs != root / "inputs" / control["runId"] or control["kind"] != kind
            or control["phase"] != "baseline"):
        raise ValueError("gather requires this run's reconciled baseline input directory")
    now = calendar.local_time(now)
    if (not calendar.run_allowed(kind, now) or now >= calendar.local_time(control["expiresAt"])
            or control["runId"][:10] != now.date().isoformat()):
        raise ValueError("input gathering outside this run's session or lease")
    return inputs, root, control


def gather(inputs, kind, now=None):
    injected_now = now
    now = now or datetime.now(timezone.utc)
    inputs, root, control = context(inputs, kind, now)
    # A completed gather is immutable; quote refreshes use convert_quotes.py.
    if (inputs / "session.json").exists():
        raise ValueError("inputs already gathered; refresh quotes only or start a new run")
    session = info(now)
    frozen = frozen_config()
    state = PortfolioState.from_dict(read_json(root / "state.json"))
    universe = read_json(ROOT / frozen["universe"]["file"])
    if hashlib.sha256(canonical_bytes(sorted(universe["passing"]))).hexdigest() != frozen["universe"]["passingSha256"]:
        raise ValueError("frozen universe hash mismatch")
    held = set(state.positions)
    pending = {ticket["ticker"] for ticket in state.pendingTickets}
    benchmarks = {C.REGIME_BENCHMARK, *C.CORE_ETFS} if kind == "morning" else set()
    required = held | pending | benchmarks
    symbols = sorted(required | (set(universe["passing"]) if kind == "morning" else set()))
    asof = session["barsAsOf"]
    fetched = data.get_daily_bars(symbols, pd.Timestamp(asof) - pd.Timedelta(days=C.HISTORY_CALENDAR_DAYS), asof)
    bars, errors = {}, {}
    for symbol in symbols:
        try:
            frame = daily_frame(fetched[symbol])
            frame = frame.loc[frame.index <= asof]
            if frame.empty or frame.index[-1].date().isoformat() != asof:
                raise ValueError("no completed bar on barsAsOf")
            bars[symbol] = frame
        except (KeyError, ValueError, TypeError):
            errors[symbol] = "missing, invalid or stale completed bars"
    atomic_json(inputs / "gather-report.json", dict(source="yfinance", barsAsOf=asof, requested=symbols, errors=errors))
    if required & errors.keys():
        raise ValueError("required portfolio/benchmark bars unavailable; see gather-report.json")
    payload = {symbol: json.loads(frame.reset_index(names="date").assign(
        date=lambda x: x.date.dt.strftime("%Y-%m-%d")).to_json(orient="records"))
        for symbol, frame in bars.items()}
    candidates = []
    if kind == "morning":
        result = screen(universe, asof, bars=bars)
        by_symbol = {row["ticker"]: row for row in result["candidates"]}
        for rank, symbol in enumerate(result["picked"], 1):
            row = by_symbol[symbol]
            cutoff = (calendar.session_open(asof) if row["moveKind"] == "gap"
                      else calendar.session_close(asof))
            if cutoff is None:
                raise ValueError("frozen calendar has no hours for the move session")
            candidates.append(row | dict(rank=rank, decisionId=f"{control['runId']}:{symbol}",
                newsCutoff=calendar.utc_stamp(cutoff), barsAsOf=asof,
                setupScore=setup_score(bars[symbol])["total"], promptVersion=prompt_version(),
                primaryAgent="manager" if rank <= 5 else "quick", quickSecondOpinionRequired=rank <= 5))
        atomic_json(inputs / "screen.json", result)
        atomic_json(inputs / "candidates.json", candidates)
        EventLog(root / f"logs/{control['runId']}.jsonl", runId=control["runId"]).append("screen", result)
    quote_symbols = sorted(held | (set(C.CORE_ETFS) | {row["ticker"] for row in candidates}
                                  if kind == "morning" else set()))
    request = dict(runId=control["runId"], kind=kind, sessionDate=session["sessionDate"],
        agent="analyst", tool="quote_market_snapshot", codes=["US." + name for name in quote_symbols],
        requiredFields=["code", "last_price", "bid_price", "ask_price", "update_time"],
        maxAgeSeconds=C.STALE_PRICE_SECONDS,
        instructions="Collect after debates, immediately before plan. Preserve raw JSON responses in quotes-raw.json; do not invent missing fields or timestamps.")
    context(inputs, kind, injected_now or datetime.now(timezone.utc))
    atomic_json(inputs / "bars.json", payload)
    atomic_json(inputs / "quote-request.json", request)
    # Written last: consumers cannot mistake a partial gather for a completed one.
    atomic_json(inputs / "session.json", session | dict(runId=control["runId"], kind=kind))
    return dict(gathered=True, kind=kind, bars=len(bars), candidates=len(candidates),
                quoteRequest=str(inputs / "quote-request.json"), barsAsOf=asof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=("morning", "watch"))
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--now", help="Aware clock override for offline rehearsal only")
    args = parser.parse_args()
    try:
        print(json.dumps(gather(args.inputs, args.kind, args.now)))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "input gathering refused; check baseline, calendar, lease and gather-report.json; retain evidence and abort\n")


if __name__ == "__main__":
    main()
