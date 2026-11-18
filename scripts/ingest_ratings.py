"""Ingest verbatim child replies into this run's log and export accepted primaries."""

import argparse
import json
from pathlib import Path
import re

import _common  # noqa: F401
from moowoo import config as C
from moowoo.events import ValidationError
from moowoo.ledger import EventLog
from moowoo.rating_schema import FIELDS, OPTIONAL_FIELDS, log_rating, parse_rating, validate_rating
from moowoo.setup_score import setup_score
from plan_session import atomic_json, load_bars

CREDITS_MISSING = "Live child agents expose no cost meter."


def require(condition, message):
    if not condition:
        raise ValidationError(message)


AGENTS = Path(__file__).resolve().parents[1] / "agents"


def with_configured_model(obj, path):
    # Agents cannot see their own deployment model id and reply model=null (17 Nov rerun 12).
    # Provenance then comes from the deployed agent definition, never from a guess.
    if isinstance(obj, dict) and "model" in obj and obj["model"] is None:
        role = Path(path).name.rsplit(".", 2)[-2]
        obj["model"] = json.loads((AGENTS / role / "agent.json").read_text(encoding="utf-8"))["model"]
    return obj


def read_reply(path):
    try:
        return parse_rating(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValidationError("missing, unreadable or malformed reply") from exc


def ingest_candidate(log, inputs, candidate, bars, session, rank):
    ticker = candidate["ticker"]
    decision = f"{log.runId}:{ticker}"
    reference = f"replies/{decision}.analyst.json"
    try:
        require(type(candidate.get("rank")) is int and candidate["rank"] == rank,
                "candidate rank differs from picked order")
        require(candidate.get("decisionId") == decision, "candidate decision identity mismatch")
        require(candidate.get("barsAsOf") == session["barsAsOf"], "candidate barsAsOf mismatch")
        require(candidate.get("primaryAgent") == "analyst", "candidate primaryAgent must be analyst")
        require(candidate.get("tier") == "single", "candidate tier must be single")
        require(ticker in bars, "missing, invalid or stale candidate bars")
        score = setup_score(bars[ticker])["total"]
        rating = validate_rating(with_configured_model(read_reply(inputs / reference), reference),
                                 candidate["newsCutoff"])
        require(rating["decisionId"] == decision and rating["ticker"] == ticker,
                "rating differs from screened decision")
        require(rating["tier"] == "single", "rating tier contradicts role")
        require(rating["promptVersion"] == candidate["promptVersion"], "rating promptVersion mismatch")
        rating.pop("quickSecondOpinion", None)
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        return log.append("halt", dict(ticker=ticker, scope="ticker",
            reason="missing or invalid candidate, bars or analyst rating reply",
            disposition="skip", stage="rating_validation", secondOpinion=False,
            transcriptRef=reference), decisionId=decision)
    return log_rating(log, rating, candidate["newsCutoff"], decision_id=decision,
        ticker=ticker, transcriptRef=reference, credits=None, creditsMissingReason=CREDITS_MISSING,
        setupScore=score, second_opinion=False)


def ingest(inputs):
    inputs = Path(inputs).resolve()
    session = read_reply(inputs / "session.json")
    run_id = session["runId"]
    require(isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", run_id), "unsafe runId")
    require(inputs.name == run_id and inputs.parent.name == "inputs" and session["kind"] == "morning",
            "expected this morning run's inputs directory")
    candidates = read_reply(inputs / "candidates.json")
    require(isinstance(candidates, list) and len(candidates) <= C.PICK_COUNT, f"expected at most {C.PICK_COUNT} candidates")
    tickers = set()
    for candidate in candidates:
        require(isinstance(candidate, dict), "candidate must be an object")
        ticker = candidate.get("ticker")
        require(isinstance(ticker, str) and re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}", ticker)
                and ticker not in tickers, "unsafe or duplicate candidate ticker")
        tickers.add(ticker)
    bars, _ = load_bars(inputs / "bars.json", session["barsAsOf"])
    log = EventLog(inputs.parent.parent / "logs" / f"{run_id}.jsonl", runId=run_id)
    with log.locked():
        outcomes = {}
        for event in log.read():
            if event["drill"]:
                continue
            if event["type"] == "rating" or (event["type"] == "halt"
                    and event.get("stage") == "rating_validation" and event.get("disposition") == "skip"):
                key = (event["decisionId"], event.get("secondOpinion", False))
                require(key not in outcomes, "duplicate terminal rating outcome")
                outcomes[key] = event
        accepted = []
        for rank, candidate in enumerate(candidates, 1):
            decision = f"{run_id}:{candidate['ticker']}"
            key = (decision, False)
            if key not in outcomes:
                outcomes[key] = ingest_candidate(log, inputs, candidate, bars, session, rank)
            primary = outcomes[(decision, False)]
            if primary and primary["type"] == "rating":
                rating = {field: primary[field] for field in FIELDS}
                validate_rating(rating, candidate["newsCutoff"])
                require(rating["tier"] == "single",
                        "replay tier must be single")
                require(rating["promptVersion"] == candidate["promptVersion"], "replay promptVersion mismatch")
                rating.update({field: primary[field] for field in OPTIONAL_FIELDS if field in primary})
                rating["setupScore"] = primary["setupScore"]
                accepted.append(rating)
        atomic_json(inputs / "ratings.json", accepted)
    return dict(accepted=len(accepted), skipped=len(candidates) - len(accepted))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(ingest(args.inputs)))
    except (ValueError, KeyError, TypeError, OSError, OverflowError, RecursionError):
        parser.exit(2, "rating ingestion refused: invalid run inputs or event log; retain evidence and abort\n")


if __name__ == "__main__":
    main()
