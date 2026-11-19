"""Auditable partial reports without fabricating missing observations."""
import math
from statistics import mean, stdev
from . import calendar
from .hypotheses import score
from .outcomes import price
from .portfolio import PortfolioState


def metrics(equities):
    result = dict(totalReturn=None, sharpe=None, sortino=None, calmar=None, maxDrawdown=None)
    if len(equities) < 2 or any(not math.isfinite(v) or v <= 0 for v in equities):
        return result
    returns = [b/a-1 for a, b in zip(equities, equities[1:])]
    peak, drawdown = equities[0], 0
    for value in equities:
        peak = max(peak, value)
        drawdown = min(drawdown, value/peak-1)
    total = equities[-1]/equities[0]-1
    deviation = stdev(returns) if len(returns) > 1 else 0
    downside = math.sqrt(mean(min(r, 0)**2 for r in returns))
    result.update(totalReturn=total, maxDrawdown=drawdown,
                  sharpe=mean(returns)/deviation*math.sqrt(252) if deviation else None,
                  sortino=mean(returns)/downside*math.sqrt(252) if downside else None)
    if drawdown:
        try:
            annual = (1+total)**(252/len(returns))-1
            if math.isfinite(annual): result["calmar"] = annual/abs(drawdown)
        except OverflowError:
            pass
    return result


def build(state, events, bars, day, previous=()):
    events = [e for e in events if not e["drill"]]
    state = PortfolioState.from_dict(state)
    missing, marks = {}, {}
    for symbol in state.positions:
        try: marks[symbol] = price(bars, symbol, day, "close")
        except ValueError: missing[f"close.{symbol}"] = "completed close unavailable"
    equity = state.equity(marks) if len(marks) == len(state.positions) else None
    hypotheses = score(events)
    brier = hypotheses["H3"]["brier"]
    if brier is None: missing["brier"] = "no completed graded primary forecasts"
    ratings = [e for e in events if e["type"] == "rating"]
    credits = sum(e["credits"] for e in ratings) if ratings and all(type(e.get("credits")) in (int, float) for e in ratings) else None
    if credits is None: missing["creditsUsed"] = "complete measured cost telemetry unavailable"
    # Raw shadow records must pass the existing paired-book validation; horizons are not trade returns.
    matched = hypotheses["H2"]["matched"]
    shadows = {book: mean(row[key] for row in matched) if matched and not hypotheses["H2"]["unavailable"] else None
               for book, key in (("llm", "llmExcess"), ("follow", "followExcess"), ("fade", "fadeExcess"))}
    for book, value in shadows.items():
        if value is None: missing[f"shadow.{book}"] = "complete matched decision-book observations unavailable"
    missing["equalWeight"] = "complete frozen-universe buy-and-hold prices at first eligible entry unavailable"
    missing["baselinePct"] = "exact SPY price at first eligible entry unavailable; daily-open comparison is a labelled proxy only"
    spy = None
    try:
        spy = price(bars, "SPY", day, "close")/price(bars, "SPY", "2026-11-17", "open")-1
    except ValueError:
        missing["spyOpenProxy"] = "SPY competition-open or session-close bar unavailable"
    prior = {r["sessionDate"]: r.get("equity") for r in previous if r["sessionDate"] < day and r.get("reconciliationVerified") is True}
    days = sorted(d.isoformat() for d in calendar.TRADING_DAYS if d.isoformat() <= day)
    values = [prior.get(d) if d != day else equity for d in days]
    # No interpolation across a missed close; that would turn a multi-day return into a daily return.
    account_metrics = metrics([100000, *values]) if all(v is not None for v in values) else metrics([])
    if any(v is None for v in values): missing["accountDailySeries"] = "missing session-close equities; daily ratios and intervals unavailable"
    for key, value in account_metrics.items():
        if value is None: missing[key] = "insufficient observations or zero denominator"
    missing["interval95"] = "complete paired account, SPY and equal-weight session-return vectors unavailable"
    today = [e for e in events if calendar.local_time(e["ts"]).date().isoformat() == day]
    return dict(sessionDate=day, equity=equity, pnlPct=(equity/100000-1)*100 if equity is not None else None,
        dailyPnlPct=(equity/state.sessionStartEquity-1)*100 if equity is not None else None,
        drawdownPct=min(0, equity/state.peakEquity-1)*100 if equity is not None else None,
        maxDrawdownPct=account_metrics["maxDrawdown"]*100 if account_metrics["maxDrawdown"] is not None else None,
        brier=brier, creditsUsed=credits, baselinePct=None, spyOpenProxyReturn=spy,
        spyOpenProxyBasis="17 Nov regular-session open to audit close; not the preregistered entry-time baseline",
        shadowMeanExcess=shadows, accountMetrics=account_metrics, hypotheses=hypotheses,
        orders=sum(e["type"] == "order_submitted" for e in today),
        vetoes=sum(e["type"] == "risk_verdict" and e["verdict"] == "veto" for e in today),
        skips=sum(e.get("executionAction") == "skip" or e.get("skipped") is True for e in today),
        missing=missing, complete=not missing, returnUnit="fraction except fields ending Pct")
