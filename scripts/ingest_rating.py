"""Validate one Qoder output and append a rating or logged skip (single writer)."""

import argparse
import json
from pathlib import Path
import _common  # noqa: F401
from moowoo.ledger import EventLog
from moowoo.rating_schema import log_rating


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("input", "log", "run-id", "ticker", "cutoff", "transcript-ref"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--credits", type=float, required=True)
    p.add_argument("--setup-score", type=int, required=True)
    p.add_argument("--second-opinion", action="store_true")
    a = p.parse_args()
    log = EventLog(a.log, runId=a.run_id)
    try:
        rating = json.loads(Path(a.input).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        log.append("halt", {"ticker": a.ticker, "scope": "ticker",
                           "reason": f"invalid rating JSON: {exc}", "disposition": "skip",
                           "stage": "rating_validation"})
        return 1
    event = log_rating(log, rating, a.cutoff, decision_id=f"{a.run_id}:{a.ticker}",
                       ticker=a.ticker, transcriptRef=a.transcript_ref, credits=a.credits,
                       setupScore=a.setup_score, second_opinion=a.second_opinion)
    print("rating accepted" if event else "rating rejected: logged skip")
    return 0 if event else 1


if __name__ == "__main__":
    raise SystemExit(main())
