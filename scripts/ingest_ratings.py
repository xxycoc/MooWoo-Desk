"""Ingest verbatim child replies into this run's log and export accepted primaries."""

import argparse
import json
from pathlib import Path
import re

import _common  # noqa: F401
from moowoo.desk_data import instant
from moowoo.events import ValidationError
from moowoo.ledger import EventLog
from moowoo.rating_schema import FIELDS, OPTIONAL_FIELDS, log_rating, parse_rating, validate_rating
from moowoo.setup_score import setup_score
from plan_session import atomic_json, load_bars

CREDITS_MISSING = "Live child agents expose no cost meter."


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def read_reply(path):
    try:
        return parse_rating(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValidationError("missing, unreadable or malformed reply") from exc


def brief_and_arguments(inputs, candidate, debate):
    decision = candidate["decisionId"]
    brief = read_reply(inputs / "replies" / f"{decision}.analyst.json")
    require(isinstance(brief, dict) and brief.get("decisionId") == decision
            and brief.get("ticker") == candidate["ticker"]
            and brief.get("newsCutoff") == candidate["newsCutoff"], "analyst identity or cutoff mismatch")
    require(isinstance(brief.get("items"), list), "analyst items must be an array")
    eligible = set()
    for item in brief["items"]:
        require(isinstance(item, dict), "invalid analyst item")
        for field in ("id", "headline", "source", "publishedAt", "summary"):
            require(isinstance(item.get(field), str) and bool(item[field].strip()), "incomplete analyst item")
        require(item["id"] not in eligible, "duplicate analyst item id")
        require(item["publishedAt"].endswith("Z")
                and instant(item["publishedAt"]) <= instant(candidate["newsCutoff"]),
                "analyst evidence after cutoff or not UTC")
        eligible.add(item["id"])
    arguments = {}
    if debate:
        for role in ("bull", "bear"):
            argument = read_reply(inputs / "replies" / f"{decision}.{role}.json")
            require(isinstance(argument, dict)
                    and set(argument) == {"decisionId", "stance", "argument", "itemIds"},
                    "invalid debate fields")
            require(argument["decisionId"] == decision and argument["stance"] == role,
                    "debate identity or stance mismatch")
            require(isinstance(argument["argument"], str) and bool(argument["argument"].strip())
                    and len(argument["argument"].split()) <= 150, "invalid debate argument")
            require(isinstance(argument["itemIds"], list)
                    and all(isinstance(item, str) and item in eligible for item in argument["itemIds"]),
                    "debate cites evidence outside the brief")
            arguments[role + "_output"] = argument
    return arguments


def ingest_candidate(log, inputs, candidate, bars, session, second_opinion, rank):
    ticker = candidate["ticker"]
    decision = f"{log.runId}:{ticker}"
    debate = rank <= 5 and not second_opinion
    role = "manager" if debate else "quick"
    reference = f"replies/{decision}.{role}.json"
    try:
        require(type(candidate.get("rank")) is int and candidate["rank"] == rank,
                "candidate rank differs from picked order")
        require(candidate.get("decisionId") == decision, "candidate decision identity mismatch")
        require(candidate.get("barsAsOf") == session["barsAsOf"], "candidate barsAsOf mismatch")
        require(candidate.get("primaryAgent") == ("manager" if rank <= 5 else "quick"),
                "candidate primaryAgent contradicts rank")
        require(candidate.get("quickSecondOpinionRequired") is (rank <= 5),
                "candidate second opinion flag contradicts rank")
        require(ticker in bars, "missing, invalid or stale candidate bars")
        score = setup_score(bars[ticker])["total"]
        arguments = brief_and_arguments(inputs, candidate, debate)
        rating = validate_rating(read_reply(inputs / reference), candidate["newsCutoff"])
        require(rating["decisionId"] == decision and rating["ticker"] == ticker,
                "rating differs from screened decision")
        require(rating["tier"] == ("debate" if debate else "quick"), "rating tier contradicts role")
        require(rating["promptVersion"] == candidate["promptVersion"], "rating promptVersion mismatch")
        rating.pop("quickSecondOpinion", None)
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError):
        return log.append("halt", dict(ticker=ticker, scope="ticker",
            reason="missing or invalid candidate, bars, analyst, debate or rating reply",
            disposition="skip", stage="rating_validation", secondOpinion=second_opinion,
            transcriptRef=reference), decisionId=decision)
    return log_rating(log, rating, candidate["newsCutoff"], decision_id=decision,
        ticker=ticker, transcriptRef=reference, credits=None, creditsMissingReason=CREDITS_MISSING,
        setupScore=score, second_opinion=second_opinion, **arguments)


def ingest(inputs):
    inputs = Path(inputs).resolve()
    session = read_reply(inputs / "session.json")
    run_id = session["runId"]
    require(isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", run_id), "unsafe runId")
    require(inputs.name == run_id and inputs.parent.name == "inputs" and session["kind"] == "morning",
            "expected this morning run's inputs directory")
    candidates = read_reply(inputs / "candidates.json")
    require(isinstance(candidates, list) and len(candidates) <= 15, "expected at most fifteen candidates")
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
            for second_opinion in ([False, True] if rank <= 5 else [False]):
                key = (decision, second_opinion)
                if key not in outcomes:
                    outcomes[key] = ingest_candidate(log, inputs, candidate, bars, session, second_opinion, rank)
            primary = outcomes[(decision, False)]
            if primary and primary["type"] == "rating":
                rating = {field: primary[field] for field in FIELDS}
                validate_rating(rating, candidate["newsCutoff"])
                require(rating["tier"] == ("debate" if rank <= 5 else "quick"),
                        "replay tier contradicts rank")
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
