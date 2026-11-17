"""Four isolated safety exercises. No drill creates or reserves an order ticket."""

from copy import deepcopy
from datetime import timedelta
import math

from . import config as C
from .desk_data import instant
from .risk import check
from .tiers import update


def run_drills(proposal, state, market, log):
    baseline = check(proposal, state, market)
    if baseline["verdict"] != "approve" or proposal["sleeve"] != "satellite" or proposal["side"] != "BUY":
        raise ValueError("drills require an otherwise approved satellite entry")
    results = []
    for name in ("stale_price", "triple_per_name_cap", "duplicate_replay", "kill_drawdown"):
        shadow, context, candidate = deepcopy(state), deepcopy(market), deepcopy(proposal)
        if name == "stale_price":
            context["quotes"][proposal["ticker"]]["ts"] = (
                instant(context["now"]) - timedelta(seconds=C.STALE_PRICE_SECONDS+1)).isoformat()
            expected = dict(verdict="veto", firedRule="stale_price")
        elif name == "triple_per_name_cap":
            candidate["qty"] = math.ceil(3*C.PER_NAME_CAP*shadow.equity(context["prices"])/candidate["limitPrice"])
            expected = dict(verdict="resize", firedRule="per_name_cap")
        elif name == "duplicate_replay":
            shadow.ticketedDecisionIds.append(candidate["decisionId"])
            expected = dict(verdict="veto", firedRule="duplicate_decision")
        else:
            update(shadow, shadow.peakEquity*(1+C.TIERS["kill"]), context["sessionDate"])
            expected = dict(verdict="veto", firedRule="kill_or_halted")
        verdict = check(candidate, shadow, context)
        observed = {key: verdict[key] for key in expected}
        passed = observed == expected
        if name == "triple_per_name_cap":
            passed = passed and verdict["qtyAfter"]*candidate["limitPrice"] <= C.PER_NAME_CAP*shadow.equity(context["prices"])
        if name == "kill_drawdown":
            passed = passed and shadow.halted and shadow.tier == "kill" and not state.halted
        result = dict(name=name, expected=expected, observed=observed, **{"pass": passed})
        log.append("drill", result, drill=True, ts=context["now"])
        results.append(result)
    return results
