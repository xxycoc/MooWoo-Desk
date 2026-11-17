"""Validate one Qoder output and append a rating or logged skip (single writer)."""

import argparse
from pathlib import Path
import _common  # noqa: F401
from moowoo.ledger import EventLog
from moowoo.rating_schema import log_rating, parse_rating


def credit_value(value):
    return None if value == "null" else float(value)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("input", "log", "run-id", "ticker", "cutoff", "transcript-ref"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--credits", type=credit_value, required=True)
    p.add_argument("--credits-missing-reason")
    p.add_argument("--setup-score", type=int, required=True)
    p.add_argument("--second-opinion", action="store_true")
    p.add_argument("--bull-output", type=Path)
    p.add_argument("--bear-output", type=Path)
    p.add_argument("--quick-output", type=Path)
    a = p.parse_args()
    log = EventLog(a.log, runId=a.run_id)
    try:
        rating = parse_rating(Path(a.input).read_text(encoding="utf-8"))
        bull = a.bull_output.read_text(encoding="utf-8") if a.bull_output else None
        bear = a.bear_output.read_text(encoding="utf-8") if a.bear_output else None
    except (ValueError, UnicodeError, OSError):
        log.append("halt", {"ticker": a.ticker, "scope": "ticker",
                           "reason": "missing or invalid rating JSON", "disposition": "skip",
                           "secondOpinion": a.second_opinion, "stage": "rating_validation"})
        return 1
    try:
        quick = a.quick_output.read_text(encoding="utf-8") if a.quick_output else None
    except (OSError, UnicodeError):
        quick = "missing quick reply"
    event = log_rating(log, rating, a.cutoff, decision_id=f"{a.run_id}:{a.ticker}",
                       ticker=a.ticker, transcriptRef=a.transcript_ref, credits=a.credits,
                       setupScore=a.setup_score, second_opinion=a.second_opinion,
                       creditsMissingReason=a.credits_missing_reason,
                       bull_output=bull, bear_output=bear,
                       quick_output=quick)
    print("rating accepted" if event else "rating rejected: logged skip")
    return 0 if event else 1


if __name__ == "__main__":
    raise SystemExit(main())
