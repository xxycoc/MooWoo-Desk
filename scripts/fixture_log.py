"""Generate fictional, deterministic trading logs; no market or broker access."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import random
import tempfile

import _common  # Sets the repository import path for direct script execution.
from moowoo.events import canonical_bytes
from moowoo.ledger import EventLog


def generate_fixture(out, seed=7, game_out=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if game_out is None:
        game_out = Path(__file__).resolve().parents[1] / "game" / "fixture" / "events.jsonl"
    rng = random.Random(seed)
    config_hash = hashlib.sha256(canonical_bytes({"seed": seed, "fixture": 0})).hexdigest()
    paths = []
    entry_price = None
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=out) as staging:
        for day in range(17, 20):
            run = f"2026-11-{day}-us"
            log = EventLog(Path(staging) / f"{run}.jsonl")
            start = datetime(2026, 11, day, 14, 30, tzinfo=timezone.utc) + timedelta(seconds=seed % 30)
            seq = 0

            def emit(kind, payload, *, drill=False, hour=None):
                nonlocal seq
                stamp = start + timedelta(seconds=seq * 45)
                if hour is not None:
                    stamp = start.replace(hour=hour, minute=0) + timedelta(seconds=seq)
                seq += 1
                return log.append(kind, payload, drill=drill, ts=stamp.isoformat().replace("+00:00", "Z"))

            price = round(252 + rng.uniform(-1.5, 1.5), 2)
            emit("run_started", dict(universe=["AAPL", "MSFT", "NVDA", "KO", "USMV", "XLP", "XLV", "IEF", "GLD"],
                 equity={17: 100000, 18: 100150, 19: 98050}[day], cash=100000 if day == 17 else 48000,
                 tier="reduced" if day == 19 else "normal", trdEnv="SIMULATE", configHash=config_hash, promptVersion="fixture-v0"))
            if day == 17:
                for etf, etf_price in (("USMV", 90), ("XLP", 84), ("XLV", 146), ("IEF", 95), ("GLD", 245)):
                    qty = int(10000 / etf_price)
                    emit("core_rebalance", dict(etf=etf, targetWeight=0.10, actualWeight=round(qty * etf_price / 100000, 5), qty=qty, side="BUY"))
            emit("screen", dict(candidates=[
                dict(ticker="AAPL", movePct=1.7, z=2.1, rvol=1.9, earnings=False),
                dict(ticker="NVDA", movePct=3.2, z=2.8, rvol=2.4, earnings=False),
                dict(ticker="KO", movePct=-1.2, z=-1.8, rvol=1.4, earnings=False),
            ], picked=["AAPL", "NVDA"]))

            def rating(ticker, tier, klass, score):
                emit("rating", {"ticker": ticker, "class": klass, "confidence": round(rng.uniform(0.58, 0.83), 3),
                     "tier": tier, "reason": "Fictional fixture: volume supports the move; news evidence remains limited.",
                     "newsCutoff": f"2026-11-{day}T14:29:00Z", "transcriptRef": f"fixture://{run}/{ticker}",
                     "credits": 3 if tier == "debate" else 1, "setupScore": score})

            rating("AAPL", "debate", "explained_up", 4)
            rating("NVDA", "quick", "unexplained_up", 3)
            if day == 18:
                rating("KO", "quick", "unexplained_down", 2)
            if day == 19:
                rating("MSFT", "debate", "explained_down", 2)
            for book, ticker, shadow_price in (("follow", "AAPL", price), ("fade", "KO", 65.2), ("equal_weight", "NVDA", 189.5)):
                emit("shadow", dict(book=book, ticker=ticker, side="BUY", notional=1000, price=shadow_price))

            def intent(ticker, qty, limit, stop, side="BUY"):
                emit("order_intent", dict(ticker=ticker, sleeve="satellite", side=side, qty=qty,
                     limitPrice=limit, notional=round(qty * limit, 2), sizing={"method": "fixed_risk", "riskBudget": 100}, stop=stop))

            def execution(ticker, qty, limit, suffix):
                order_id = f"SIM-{day}-{suffix}"
                emit("order_submitted", dict(ticker=ticker, orderId=order_id, qty=qty, limitPrice=limit, trdEnv="SIMULATE"))
                emit("fill", dict(ticker=ticker, orderId=order_id, filledQty=qty, avgPrice=limit, status="FILLED", source="order_status"))
                return order_id

            if day == 17:
                entry_price = price
                intent("AAPL", 12, price, 245)
                emit("risk_verdict", dict(ticker="AAPL", verdict="approve", rules=["long_only", "cash", "correlation"], firedRule=None, qtyAfter=12))
                execution("AAPL", 12, price, "AAPL-BUY")
                intent("NVDA", 10, 189.5, 183)
                emit("risk_verdict", dict(ticker="NVDA", verdict="veto", rules=["long_only", "cash", "correlation"], firedRule="correlation", qtyAfter=0))
                emit("drill", {"name": "stale_price", "expected": "veto", "observed": "veto", "pass": True}, drill=True)
                emit("reflection_note", dict(prompt="What would invalidate today's thesis?", text="A volume reversal without supporting news would weaken it. Fixture only."))
            elif day == 18:
                emit("tier_changed", {"from": "normal", "to": "reduced", "drawdownPct": 2.1, "peakEquity": 100150})
                intent("AAPL", 12, 244.8, 245, side="SELL")
                emit("risk_verdict", dict(ticker="AAPL", verdict="approve", rules=["long_only", "position_qty"], firedRule=None, qtyAfter=12))
                emit("stop_hit", dict(ticker="AAPL", entry=entry_price, stop=245, exitOrderId="SIM-18-AAPL-STOP"))
                execution("AAPL", 12, 244.8, "AAPL-STOP")
                intent("MSFT", 8, 510, 498)
                emit("risk_verdict", dict(ticker="MSFT", verdict="resize", rules=["long_only", "cash", "tier_size"], firedRule="tier_size", qtyAfter=4))
                execution("MSFT", 4, 510, "MSFT-BUY")
                emit("halt", dict(ticker="NVDA", reason="Correlation veto remains active for this run.", scope="ticker"))
                emit("rule_change", dict(ruleId="correlation", before={"maxPairCorrelation": 0.85}, after={"maxPairCorrelation": 0.80},
                     triggerDecisionIds=["2026-11-17-us:NVDA"], effectiveFrom="2026-11-19T14:30:00Z"))
                emit("reflection_note", dict(prompt="Did the process protect capital?", text="The stop closed the position; reduced sizing limited the next entry. Fixture only."))
            else:
                emit("tier_changed", {"from": "reduced", "to": "normal", "drawdownPct": 0.3, "peakEquity": 100150})
                intent("NVDA", 6, 189.5, 183)
                emit("risk_verdict", dict(ticker="NVDA", verdict="approve", rules=["long_only", "cash", "correlation"], firedRule=None, qtyAfter=6))
                execution("NVDA", 6, 189.5, "NVDA-BUY")
            emit("daily_report", dict(equity={17: 100150, 18: 98050, 19: 99850}[day], pnlPct={17: 0.15, 18: -1.95, 19: -0.15}[day],
                 baselinePct=0.12, shadowPct={"follow": 0.2, "fade": -0.1, "equal_weight": 0.08}, brier=0.21,
                 maxDrawdownPct=0.4 if day == 17 else 2.1, orders=2 if day == 18 else 1, vetoes=1 if day == 17 else 0,
                 skips=1, creditsUsed=4 if day == 17 else (5 if day == 18 else 7)), hour=21)
            paths.append(out / f"{run}.jsonl")
        for path in paths:
            os.replace(Path(staging) / path.name, path)
    game_out = Path(game_out)
    game_out.parent.mkdir(parents=True, exist_ok=True)
    game_out.write_bytes(paths[-1].read_bytes())
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="fixtures/")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--game-out", default=None, help="Override game/fixture/events.jsonl (useful for isolated tests)")
    args = parser.parse_args()
    for path in generate_fixture(args.out, args.seed, args.game_out):
        print(f"OK {path}")
    print(f"OK {args.game_out or 'game/fixture/events.jsonl'}: copied 2026-11-19-us.jsonl")


if __name__ == "__main__":
    main()
