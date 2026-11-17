"""Strict model-output boundary. No sizing, broker access, or implicit cutoff."""

from copy import deepcopy
from datetime import datetime
import math
import re

from .events import ValidationError

CLASSES = ("explained_up", "explained_down", "unexplained_up", "unexplained_down")
FIELDS = {"decisionId", "ticker", "class", "confidence", "tier", "reason", "evidence",
          "newsCutoff", "expectedMove", "wrongIf", "model", "promptVersion"}


def _require(ok, message):
    if not ok:
        raise ValidationError(message)


def _object(obj, fields, name):
    _require(type(obj) is dict, f"{name} must be an object")
    _require(set(obj) == fields, f"{name} has missing or unknown fields")


def _text(value, name):
    _require(type(value) is str and bool(value.strip()), f"{name} must be nonempty text")


def _timestamp(value, name):
    _text(value, name)
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", value) is not None,
             f"{name} must be an RFC3339 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"invalid {name}") from exc


def validate_rating(obj, cutoff):
    """Raise ValidationError on invalid output; cutoff is trusted caller input.

    A valid result is returned as a detached dictionary. Directions describe the
    preregistered forecast, not an instruction to buy or short.
    """
    _object(obj, FIELDS, "rating")
    for field in ("decisionId", "ticker", "reason", "wrongIf", "model", "promptVersion"):
        _text(obj[field], field)
    _require(obj["decisionId"].endswith(":" + obj["ticker"]) and
             len(obj["decisionId"]) > len(obj["ticker"]) + 1, "decisionId must be runId:TICKER")
    _require(obj["class"] in CLASSES, "invalid class")
    _require(obj["tier"] in ("debate", "quick"), "invalid tier")
    confidence = obj["confidence"]
    _require(type(confidence) in (int, float) and 0 <= confidence <= 1 and
             math.isfinite(confidence), "confidence must be a finite number from 0 to 1")
    _require(len(obj["reason"]) <= 600, "reason exceeds 600 characters")
    bound = _timestamp(cutoff, "cutoff")
    _require(_timestamp(obj["newsCutoff"], "newsCutoff") == bound, "newsCutoff differs from trusted cutoff")
    _require(type(obj["evidence"]) is list, "evidence must be an array")
    ids = set()
    for item in obj["evidence"]:
        _object(item, {"id", "headline", "source", "publishedAt"}, "evidence item")
        for field in ("id", "headline", "source"):
            _text(item[field], field)
        _require(item["id"] not in ids, "duplicate evidence id")
        ids.add(item["id"])
        _require(_timestamp(item["publishedAt"], "publishedAt") <= bound, "lookahead: evidence after cutoff")
    move = obj["expectedMove"]
    _object(move, {"direction", "horizon"}, "expectedMove")
    explained = obj["class"].startswith("explained_")
    direction = obj["class"].rsplit("_", 1)[1]
    if not explained:
        direction = "down" if direction == "up" else "up"
    _require(move["direction"] == direction, "expectedMove.direction contradicts class")
    _require(type(move["horizon"]) is int and move["horizon"] == (5 if explained else 3),
             "expectedMove.horizon contradicts class")
    return deepcopy(obj)


def _finite_nonnegative(value):
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def rating_to_event(obj, cutoff, *, transcriptRef, credits, setupScore, second_opinion=False):
    """Return EventLog rating payload; pass decisionId separately to append.

    Runtime supplies actual transcript/credit data and code-computed setup score.
    Never fabricate defaults for missing event-contract fields.
    """
    rating = validate_rating(obj, cutoff)
    _text(transcriptRef, "transcriptRef")
    _require(_finite_nonnegative(credits),
             "credits must be finite and nonnegative")
    _require(type(setupScore) is int and 0 <= setupScore <= 5, "setupScore must be integer 0..5")
    _require(type(second_opinion) is bool, "second_opinion must be bool")
    rating.pop("decisionId")
    rating.update(transcriptRef=transcriptRef, credits=credits, setupScore=setupScore,
                  secondOpinion=second_opinion)
    return rating


def log_rating(log, obj, cutoff, *, decision_id, ticker, transcriptRef, credits, setupScore,
               second_opinion=False):
    """Single-writer ingestion: reject to a ticker halt with disposition=skip.

    Identity comes from the screened mover, never from untrusted model output.
    Second opinions are rating events but must not become risk-desk inputs.
    """
    _require(decision_id == f"{log.runId}:{ticker}", "trusted decision identity mismatch")
    try:
        payload = rating_to_event(obj, cutoff, transcriptRef=transcriptRef, credits=credits,
                                  setupScore=setupScore, second_opinion=second_opinion)
        _require(obj["decisionId"] == decision_id and obj["ticker"] == ticker,
                 "rating differs from screened decision")
    except ValidationError as exc:
        log.append("halt", {"ticker": ticker, "scope": "ticker", "reason": str(exc),
                            "disposition": "skip", "stage": "rating_validation",
                            "secondOpinion": second_opinion,
                            "transcriptRef": transcriptRef if isinstance(transcriptRef, str) else ""},
                   decisionId=decision_id)
        return None
    return log.append("rating", payload, decisionId=decision_id)
