"""Version 0 event contract and canonical JSON encoding."""

from datetime import datetime
import hashlib
import json
import math
import re


ZERO_HASH = "0" * 64
COMMON_FIELDS = frozenset(
    ("v", "runId", "seq", "ts", "decisionId", "type", "drill", "prevHash", "hash")
)
REQUIRED_FIELDS = {
    "run_started": ("universe", "equity", "cash", "tier", "trdEnv", "configHash", "promptVersion"),
    "screen": ("candidates", "picked"),
    "rating": ("ticker", "class", "confidence", "tier", "reason", "newsCutoff", "transcriptRef", "credits", "setupScore"),
    "outcome": ("ticker", "class", "confidence", "horizonSessions", "entryTs", "entryPrice",
                "exitTs", "exitPrice", "stockReturn", "spyReturn", "excess", "right", "graded",
                "sourceRunId", "ratingHash", "ratingTs", "newsCutoff", "forecastDirection", "secondOpinion"),
    "shadow": ("book", "ticker", "side", "notional", "price"),
    "core_rebalance": ("etf", "targetWeight", "actualWeight", "qty", "side"),
    "order_intent": ("ticker", "sleeve", "side", "qty", "limitPrice", "notional", "sizing", "stop"),
    "risk_verdict": ("ticker", "verdict", "rules", "firedRule", "qtyAfter"),
    "order_submitted": ("ticker", "orderId", "qty", "limitPrice", "trdEnv"),
    "fill": ("ticker", "orderId", "filledQty", "avgPrice", "status", "source"),
    "stop_hit": ("ticker", "entry", "stop", "exitOrderId"),
    "tier_changed": ("from", "to", "drawdownPct", "peakEquity"),
    "halt": ("reason", "scope"),
    "drill": ("name", "expected", "observed", "pass"),
    "rule_change": ("ruleId", "before", "after", "triggerDecisionIds", "effectiveFrom"),
    "reflection_note": ("prompt", "text"),
    "daily_report": ("equity", "pnlPct", "baselinePct", "shadowPct", "brier", "maxDrawdownPct", "orders", "vetoes", "skips", "creditsUsed"),
}
EVENT_TYPES = frozenset(REQUIRED_FIELDS)


class ValidationError(ValueError):
    """An event violates the version 0 contract."""


def canonical_bytes(obj: dict) -> bytes:
    """Canonical UTF-8 JSON; nonfinite numbers are not JSON values."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def event_hash(event: dict) -> str:
    return hashlib.sha256(canonical_bytes({k: v for k, v in event.items() if k != "hash"})).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _json_value(value, path="event") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _require(isinstance(key, str), f"{path}: JSON keys must be strings")
            if key == "trdEnv":
                _require(child == "SIMULATE", f"{path}.trdEnv must be SIMULATE")
            _json_value(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            _json_value(child, path)
    else:
        _require(value is None or type(value) in (str, int, float, bool), f"{path}: invalid JSON value")
        if type(value) is float:
            _require(math.isfinite(value), f"{path}: number must be finite")


def _string(value, name):
    _require(isinstance(value, str), f"{name} must be a string")


def _number(value, name):
    _require(type(value) in (int, float), f"{name} must be a number")


def _enum(value, choices, name):
    _require(value in choices, f"{name} must be one of {', '.join(choices)}")


def _utc(value, name):
    _string(value, name)
    _require(value.endswith("Z") and "T" in value, f"{name} must be ISO 8601 UTC with Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{name} must be ISO 8601 UTC with Z") from exc


def validate_event(event: dict) -> None:
    """Validate shape and safety rules; chain integrity is checked by verify()."""
    _require(isinstance(event, dict), "event must be an object")
    _json_value(event)
    missing = COMMON_FIELDS - event.keys()
    _require(not missing, f"missing common fields: {', '.join(sorted(missing))}")
    _require(type(event["v"]) is int and event["v"] == 0, "v must be integer 0")
    _require(isinstance(event["runId"], str) and bool(event["runId"]), "runId must be nonempty")
    _require(type(event["seq"]) is int and event["seq"] >= 1, "seq must be a positive integer")
    _utc(event["ts"], "ts")
    _require(type(event["drill"]) is bool, "drill must be a bool")
    for field in ("hash", "prevHash"):
        _require(isinstance(event[field], str) and re.fullmatch(r"[0-9a-f]{64}", event[field]) is not None,
                 f"{field} must be 64 lowercase hexadecimal characters")
    kind = event["type"]
    _require(isinstance(kind, str) and kind in REQUIRED_FIELDS, f"unknown type: {kind!r}")
    missing = set(REQUIRED_FIELDS[kind]) - event.keys()
    _require(not missing, f"{kind}: missing fields: {', '.join(sorted(missing))}")
    decision = event["decisionId"]
    decision_run = event.get("sourceRunId") if kind == "outcome" else event["runId"]
    _require(isinstance(decision_run, str) and bool(decision_run), "invalid source run")
    _require(decision is None or (isinstance(decision, str) and
             decision.startswith(decision_run + ":") and
             bool(decision[len(decision_run) + 1:])), "decisionId must be null or runId:TICKER")
    ticker = event.get("ticker", event.get("etf"))
    if ticker is not None:
        _require(isinstance(ticker, str) and bool(ticker), "ticker/etf must be a nonempty string")
        _require(decision == f"{decision_run}:{ticker}", "decisionId must match runId:TICKER")

    number_fields = {
        "equity", "cash", "confidence", "credits", "notional", "price", "targetWeight", "actualWeight",
        "qty", "limitPrice", "stop", "qtyAfter", "filledQty", "avgPrice", "entry", "drawdownPct",
        "peakEquity", "pnlPct", "baselinePct", "brier", "maxDrawdownPct", "creditsUsed",
    }
    list_fields = {"universe", "picked", "rules", "triggerDecisionIds"}
    object_fields = {"sizing", "shadowPct"}
    arbitrary_fields = {"before", "after", "expected", "observed"}
    for field in REQUIRED_FIELDS[kind]:
        value = event[field]
        if kind == "outcome":
            continue
        if kind == "rating" and field == "credits" and value is None:
            _string(event.get("creditsMissingReason"), "creditsMissingReason")
            _require(bool(event["creditsMissingReason"].strip()), "creditsMissingReason must be nonempty")
            continue
        if field in number_fields:
            _number(value, field)
        elif field in list_fields:
            _require(isinstance(value, list) and all(isinstance(x, str) for x in value), f"{field} must be a list of strings")
        elif field in object_fields:
            _require(isinstance(value, dict), f"{field} must be an object")
        elif field in ("setupScore", "orders", "vetoes", "skips"):
            _require(type(value) is int and value >= 0, f"{field} must be a nonnegative integer")
        elif field == "pass":
            _require(type(value) is bool, "pass must be a bool")
        elif field == "firedRule":
            _require(value is None or isinstance(value, str), "firedRule must be a string or null")
        elif field not in arbitrary_fields and field != "candidates":
            _string(value, field)

    if kind == "screen":
        _require(isinstance(event["candidates"], list), "candidates must be a list")
        for item in event["candidates"]:
            _require(isinstance(item, dict) and {"ticker", "movePct", "z", "rvol", "earnings"} <= item.keys(),
                     "each candidate requires ticker, movePct, z, rvol, earnings")
            _string(item["ticker"], "candidate.ticker")
            for field in ("movePct", "z", "rvol"):
                _number(item[field], f"candidate.{field}")
    elif kind == "rating":
        from .rating_schema import validate_debate
        validate_debate(event)
        if event["credits"] is not None:
            _require(event["credits"] >= 0, "credits must be nonnegative")
            _require(event.get("creditsMissingReason") is None, "measured credits cannot have a missing reason")
        _enum(event["class"], ("explained_up", "explained_down", "unexplained_up", "unexplained_down"), "class")
        _enum(event["tier"], ("debate", "quick", "single"), "tier")
        _require(0 <= event["confidence"] <= 1, "confidence must be between 0 and 1")
        _require(event["setupScore"] <= 5, "setupScore must be between 0 and 5")
        _utc(event["newsCutoff"], "newsCutoff")
    elif kind == "outcome":
        from .rating_schema import CLASSES
        _require(isinstance(event["ticker"], str) and bool(event["ticker"]), "outcome ticker required")
        _enum(event["class"], CLASSES, "class")
        _number(event["confidence"], "confidence")
        _require(0 <= event["confidence"] <= 1, "invalid outcome confidence")
        explained = event["class"].startswith("explained_")
        direction = event["class"].rsplit("_", 1)[1]
        forecast = direction if explained else ("up" if direction == "down" else "down")
        _require(event["forecastDirection"] == forecast, "outcome forecast contradicts class")
        _require(type(event["horizonSessions"]) is int and event["horizonSessions"] == (5 if explained else 3),
                 "outcome horizon contradicts class")
        _require(isinstance(event["ratingHash"], str) and re.fullmatch(r"[0-9a-f]{64}", event["ratingHash"]) is not None,
                 "invalid ratingHash")
        for field in ("ratingTs", "newsCutoff"):
            _utc(event[field], field)
        for field in ("graded", "right", "secondOpinion"):
            _require(type(event[field]) is bool, f"{field} must be bool")
        for field in ("entryTs", "exitTs"):
            if event[field] is not None:
                _utc(event[field], field)
            else:
                _require(not event["graded"], f"graded {field} required")
        for field in ("entryPrice", "exitPrice", "stockReturn", "spyReturn", "excess"):
            if event[field] is not None:
                _number(event[field], field)
                if field.endswith("Price"):
                    _require(event[field] > 0, f"{field} must be positive")
            else:
                _require(not event["graded"], f"graded {field} required")
        if event["graded"]:
            _require(datetime.fromisoformat(event["ratingTs"].replace("Z", "+00:00"))
                     < datetime.fromisoformat(event["entryTs"].replace("Z", "+00:00"))
                     < datetime.fromisoformat(event["exitTs"].replace("Z", "+00:00")), "invalid outcome chronology")
            _require(math.isclose(event["stockReturn"], event["exitPrice"] / event["entryPrice"] - 1,
                                  abs_tol=1e-12), "outcome stock return mismatch")
            _require(math.isclose(event["excess"], event["stockReturn"] - event["spyReturn"], abs_tol=1e-12),
                     "outcome excess mismatch")
            _require(event["right"] == (event["excess"] > 0 if forecast == "up" else event["excess"] < 0),
                     "outcome right mismatch")
        else:
            _require(isinstance(event.get("reason"), str) and bool(event["reason"].strip()), "ungraded reason required")
            _require(event["right"] is False, "ungraded right must be false")
    elif kind == "shadow":
        _enum(event["book"], ("llm", "follow", "fade", "equal_weight"), "book")
    elif kind == "order_intent":
        _enum(event["sleeve"], ("core", "satellite"), "sleeve")
    elif kind == "risk_verdict":
        _enum(event["verdict"], ("approve", "resize", "veto"), "verdict")
    elif kind == "fill":
        _require(event["source"] == "order_status", "fill.source must be order_status")
    elif kind == "halt":
        _enum(event["scope"], ("ticker", "run", "all"), "scope")
    elif kind == "drill":
        _require(event["drill"], "drill events must have drill=true")
    elif kind == "daily_report":
        _require({"follow", "fade", "equal_weight"} <= event["shadowPct"].keys(), "shadowPct requires all three books")
        for book in ("follow", "fade", "equal_weight"):
            _number(event["shadowPct"][book], f"shadowPct.{book}")
