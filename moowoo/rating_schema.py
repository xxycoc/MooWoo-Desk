"""Strict model-output boundary. No sizing, broker access, or implicit cutoff."""

from copy import deepcopy
from datetime import datetime
import json
import logging
import math
import re

from .events import ValidationError

CLASSES = ("explained_up", "explained_down", "unexplained_up", "unexplained_down")
FIELDS = {"decisionId", "ticker", "class", "confidence", "tier", "reason", "evidence",
          "newsCutoff", "expectedMove", "wrongIf", "model", "promptVersion"}
OPTIONAL_FIELDS = {"bullSummary", "bearSummary", "quickSecondOpinion"}


def parse_rating(text):
    """Decode JSON, tolerating only a single complete fenced JSON block."""
    _require(isinstance(text, str), "output must be text")
    match = re.fullmatch(r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*", text, re.DOTALL)
    if match:
        text = match[1]
        logging.getLogger(__name__).warning("Stripped single JSON code fence from rating output")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("non-JSON numeric constant")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError) as exc:
        raise ValidationError("malformed output JSON") from exc


def validate_debate(obj):
    for field in ("bullSummary", "bearSummary"):
        if field in obj:
            _text(obj[field], field)
            _require(len(obj[field]) <= 600, f"{field} exceeds 600 characters")
    if "quickSecondOpinion" in obj:
        opinion = obj["quickSecondOpinion"]
        _object(opinion, {"class", "confidence"}, "quickSecondOpinion")
        _require(opinion["class"] in CLASSES, "invalid quickSecondOpinion class")
        _require(type(opinion["confidence"]) in (int, float) and
                 0 <= opinion["confidence"] <= 1, "invalid quickSecondOpinion confidence")


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
    _require(type(obj) is dict and FIELDS <= obj.keys() and
             not obj.keys() - FIELDS - OPTIONAL_FIELDS, "rating has missing or unknown fields")
    validate_debate(obj)
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


def rating_to_event(obj, cutoff, *, transcriptRef, credits, setupScore, second_opinion=False,
                    bull_output=None, bear_output=None, quick_output=None, creditsMissingReason=None):
    """Return EventLog rating payload; pass decisionId separately to append.

    Runtime supplies actual transcript/credit data and code-computed setup score.
    Never fabricate defaults for missing event-contract fields.
    """
    rating = validate_rating(obj, cutoff)
    for field, output in (("bullSummary", bull_output), ("bearSummary", bear_output)):
        if output is not None:
            argument = parse_rating(output) if isinstance(output, str) else output
            _require(isinstance(argument, dict), "debate output must be an object")
            _require(argument.get("decisionId") == rating["decisionId"]
                     and argument.get("stance") == field.removesuffix("Summary"),
                     "debate output identity or stance mismatch")
            _text(argument.get("argument"), field)
            rating[field] = argument["argument"].strip()[:600]
    if quick_output is not None:
        quick = validate_rating(quick_output, cutoff)
        _require(quick["decisionId"] == rating["decisionId"] and quick["ticker"] == rating["ticker"]
                 and quick["tier"] == "quick", "second opinion identity or tier mismatch")
        rating["quickSecondOpinion"] = {key: quick[key] for key in ("class", "confidence")}
    _text(transcriptRef, "transcriptRef")
    if credits is None:
        _text(creditsMissingReason, "creditsMissingReason")
        rating["creditsMissingReason"] = creditsMissingReason
    else:
        _require(_finite_nonnegative(credits), "credits must be finite and nonnegative")
        _require(creditsMissingReason is None, "measured credits cannot have a missing reason")
    _require(type(setupScore) is int and 0 <= setupScore <= 5, "setupScore must be integer 0..5")
    _require(type(second_opinion) is bool, "second_opinion must be bool")
    rating.pop("decisionId")
    rating.update(transcriptRef=transcriptRef, credits=credits, setupScore=setupScore,
                  secondOpinion=second_opinion)
    return rating


def log_rating(log, obj, cutoff, *, decision_id, ticker, transcriptRef, credits, setupScore,
               second_opinion=False, bull_output=None, bear_output=None, quick_output=None,
               creditsMissingReason=None):
    """Single-writer ingestion: reject to a ticker halt with disposition=skip.

    Identity comes from the screened mover, never from untrusted model output.
    Second opinions are rating events but must not become risk-desk inputs.
    """
    _require(decision_id == f"{log.runId}:{ticker}", "trusted decision identity mismatch")
    try:
        payload = rating_to_event(obj, cutoff, transcriptRef=transcriptRef, credits=credits,
                                  setupScore=setupScore, second_opinion=second_opinion,
                                  bull_output=bull_output, bear_output=bear_output,
                                  creditsMissingReason=creditsMissingReason)
        _require(obj["decisionId"] == decision_id and obj["ticker"] == ticker,
                 "rating differs from screened decision")
    except ValidationError as exc:
        log.append("halt", {"ticker": ticker, "scope": "ticker", "reason": str(exc),
                            "disposition": "skip", "stage": "rating_validation",
                            "secondOpinion": second_opinion,
                            "transcriptRef": transcriptRef if isinstance(transcriptRef, str) else ""},
                   decisionId=decision_id)
        return None
    quick_payload = None
    quick_error = None
    if quick_output is not None:
        try:
            quick = parse_rating(quick_output) if isinstance(quick_output, str) else quick_output
            quick_payload = rating_to_event(quick, cutoff, transcriptRef=transcriptRef,
                credits=None, setupScore=setupScore, second_opinion=True,
                creditsMissingReason="Separate quick credit usage was not supplied.")
            _require(quick["decisionId"] == decision_id and quick["ticker"] == ticker
                     and quick["tier"] == "quick", "second opinion identity or tier mismatch")
            payload["quickSecondOpinion"] = {key: quick[key] for key in ("class", "confidence")}
        except ValidationError as exc:
            quick_payload = None
            quick_error = str(exc)
    event = log.append("rating", payload, decisionId=decision_id)
    if quick_payload is not None:
        log.append("rating", quick_payload, decisionId=decision_id)
    elif quick_error:
        log.append("halt", dict(ticker=ticker, scope="ticker", reason=quick_error,
            disposition="skip", stage="rating_validation", secondOpinion=True,
            transcriptRef=transcriptRef), decisionId=decision_id)
    return event
