"""Peak drawdown tiers, latched daily halt, and session-observed recovery."""

from datetime import date

from . import config as C
from .portfolio import positive

LEVELS = ("normal", "reduced", "exits_only", "kill")


def update(state, equity, session, *, at_close=False, at_open=False):
    positive(equity, "equity", zero=True)
    date.fromisoformat(session)
    if state.sessionDate and session < state.sessionDate:
        raise ValueError("session cannot go backwards")
    if state.sessionDate != session:
        if state.sessionDate is not None:
            state.sessionStartEquity = equity
            state.ordersPlacedThisSession = 0
            state.dailyLossHalted = False
        state.sessionDate = session
    state.peakEquity = max(state.peakEquity, equity)
    drawdown = equity / state.peakEquity - 1
    triggered = "normal"
    for tier, threshold in C.TIERS.items():
        if drawdown <= threshold + 1e-12:
            triggered = tier
    events = []
    previous = state.tier
    if state.tier == "kill":
        state.halted = True
    elif LEVELS.index(triggered) > LEVELS.index(state.tier):
        state.tier = triggered
        state.recoverySince = state.recoveryTier = None
    elif LEVELS.index(triggered) < LEVELS.index(state.tier):
        if state.recoveryTier != triggered:
            state.recoveryTier = triggered
            state.recoverySince = session
            state.recoveryFromOpen = at_open
        full_session = session > state.recoverySince or state.recoveryFromOpen
        if at_close and full_session:
            state.tier = triggered
            state.recoverySince = state.recoveryTier = None
    else:
        state.recoverySince = state.recoveryTier = None
    if previous != state.tier:
        events.append(dict(type="tier_changed", **{"from": previous, "to": state.tier},
                           drawdownPct=drawdown * 100, peakEquity=state.peakEquity))
    if state.tier == "kill" and state.haltReason != "peak drawdown kill":
        state.halted, state.haltReason = True, "peak drawdown kill"
        events.append(dict(type="halt", reason=state.haltReason, scope="all",
                           cancelEntries=True, liquidate=True))
    if equity <= state.sessionStartEquity * (1 - C.DAILY_LOSS_HALT) + 1e-9:
        if not state.dailyLossHalted:
            state.dailyLossHalted = True
            events.append(dict(type="halt", reason="daily loss limit", scope="run"))
    return events
