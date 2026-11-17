"""Close-only, matched-decision step-up and permanent satellite invalidation."""

from copy import deepcopy
from datetime import date
import math
from statistics import mean

from . import config as C


def _matched(rows, flag, keys):
    matched, missing, seen = [], [], set()
    for row in rows:
        if not row.get(flag, True):
            continue
        decision = row["decisionId"]
        if decision in seen:
            raise ValueError(f"duplicate completed decision: {decision}")
        seen.add(decision)
        values = [row.get(key) for key in keys]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in values):
            missing.append(decision)
        else:
            matched.append(row)
    result = dict(count=len(matched), decisionIds=[row["decisionId"] for row in matched], missing=missing)
    for key in keys:
        result[key] = mean(row[key] for row in matched) if matched else None
    return result


def evaluate(graded_calls, closed_trades, session, next_session, *, at_close, previous=None):
    date.fromisoformat(session)
    date.fromisoformat(next_session)
    if next_session <= session:
        raise ValueError("next_session must be a later trading session")
    state = deepcopy(previous or dict(enabled=False, invalidated=False))
    calls = _matched(graded_calls, "graded", ("llmExcess", "followExcess"))
    trades = _matched([row for row in closed_trades if row.get("sleeve") == "satellite"], "closed", ("llmExcess", "followExcess", "fadeExcess"))
    evidence = dict(gradedCalls=calls, closedSatelliteTrades=trades, evaluatedSession=session)
    if not at_close:
        return dict(decision="defer_until_close", state=state, evidence=evidence)
    if state.get("invalidated"):
        return dict(decision="invalidated", state=state, evidence=evidence)
    if (trades["count"] >= 15 and not trades["missing"] and
            trades["llmExcess"] < max(trades["followExcess"], trades["fadeExcess"])):
        state.update(enabled=False, invalidated=True, invalidatedOn=session, thesis="failed")
        return dict(decision="invalidate", state=state, evidence=evidence)
    if (not state.get("enabled") and calls["count"] >= C.STEP_UP_MIN_GRADED_CALLS and
            not calls["missing"] and calls["llmExcess"] > calls["followExcess"]):
        state.update(enabled=True, effectiveFrom=next_session)
        return dict(decision="step_up_next_session", state=state, evidence=evidence)
    return dict(decision="unchanged", state=state, evidence=evidence)
