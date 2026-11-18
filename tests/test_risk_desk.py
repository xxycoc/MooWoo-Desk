"""Synthetic decision-desk checks; no broker or data-provider calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from moowoo import config as C
from moowoo.core import weights, propose_core
from moowoo.desk_data import limit_price, regime_filter
from moowoo.drills import run_drills
from moowoo.events import canonical_bytes
from moowoo.exits import propose_exits
from moowoo.fees import estimate_fees, realized_pnl
from moowoo.ledger import EventLog, verify
from moowoo.portfolio import PortfolioState
from moowoo.risk import RULES, check
from moowoo.sizing import propose_entry
from moowoo.stepup import evaluate
from moowoo.tickets import OrderTicket, to_sim_order, verify_placed, reconcile_fill
from moowoo.tiers import update

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-11-17T15:00:00Z"
RUN = "2026-11-17-us"


def bars(seed=1, end="2026-11-16", n=130):
    rng = np.random.default_rng(seed)
    close = 100*np.cumprod(1 + .002 + rng.uniform(-.003, .003, n))
    return pd.DataFrame(dict(open=close, high=close+1, low=close-1,
                             close=close, volume=np.full(n, 2_000_000.)),
                        index=pd.bdate_range(end=end, periods=n))


def position(kind="drift", qty=20, **changes):
    return dict(qty=qty, avgCost=100., sleeve="core" if kind == "core" else "satellite",
                kind=kind, entryDate="2026-11-17", entryPrice=100., stop=90.,
                trailArmed=False, highestClose=100., preDropClose=120., signalAtr=2.,
                decisionId="previous:AAA") | changes


@pytest.fixture
def desk():
    state = PortfolioState(cash=100000, sessionDate="2026-11-17")
    proposal = dict(ticker="AAA", decisionId=f"{RUN}:AAA", side="BUY", qty=50,
                    limitPrice=100., sleeve="satellite", kind="drift", stop=94.,
                    reason="synthetic drift", sizing={}, signalAtr=2.)
    frames = {ticker: bars(i+1) for i, ticker in enumerate(["AAA", "BBB", "CCC", "DDD", "SPY", *C.CORE_ETFS])}
    frames["SPY"] = bars(1)
    quotes = {ticker: dict(last=100., bid=99.95, ask=100., ts=NOW) for ticker in frames}
    market = dict(now=NOW, sessionDate="2026-11-17", prices={t: 100. for t in frames},
                  bars=frames, quotes=quotes, minutesSinceOpen=30, isRegularSession=True)
    assert not regime_filter(frames["SPY"])
    return proposal, state, market


def test_portfolio_roundtrip_and_reservations(desk):
    p, s, m = desk
    s.positions["BBB"] = position(qty=10)
    assert s.equity(m["prices"]) == 101000
    assert PortfolioState.from_json(s.to_json()).to_dict() == s.to_dict()
    ticket = OrderTicket.from_proposal(p, check(p, s, m), "a"*64, NOW)
    s.reserve(ticket)
    assert s.reservedCash == 5000.99
    assert s.exposure(m["prices"], sleeve="satellite") == 6000
    assert s.equity(m["prices"]) == 101000
    with pytest.raises(ValueError, match="already ticketed"):
        s.reserve(ticket)


@pytest.mark.parametrize("rule", RULES)
def test_every_rule_independently_in_order(desk, rule):
    p, s, m = desk
    expected = "veto"
    if rule == "kill_or_halted": s.halted = True
    elif rule == "exits_only": s.tier = "exits_only"
    elif rule == "daily_loss": s.sessionStartEquity = 102000
    elif rule == "final_day": m["sessionDate"] = C.FINAL_DAY
    elif rule == "first_minutes": m["minutesSinceOpen"] = 4.99
    elif rule == "regime":
        p["kind"] = "bounce"
        m["bars"]["SPY"].iloc[-1] = [50, 51, 49, 50, 2_000_000]
    elif rule == "duplicate_decision": s.ticketedDecisionIds.append(p["decisionId"])
    elif rule == "max_orders": s.ordersPlacedThisSession = 30
    elif rule == "stale_price": m["quotes"]["AAA"]["ts"] = "2026-11-17T14:58:59Z"
    elif rule == "spread": m["quotes"]["AAA"]["bid"] = 99
    elif rule == "correlation":
        s.positions["BBB"] = position()
        m["bars"]["BBB"] = m["bars"]["AAA"].copy()
    elif rule == "bounce_count":
        p["kind"] = "bounce"
        for ticker in ("BBB", "CCC", "DDD"): s.positions[ticker] = position("bounce")
    elif rule == "satellite_invalidated": s.stepUp["invalidated"] = True
    elif rule == "per_name_cap":
        p["qty"] = 240
        expected = "resize"
    elif rule == "satellite_cap":
        s.positions["BBB"] = position(qty=220)
        s.cash = 78000
        expected = "resize"
    elif rule == "cash_floor":
        s.positions["USMV"] = position("core", qty=870)
        s.cash = 13000
        expected = "resize"
    elif rule == "adv":
        m["bars"]["AAA"]["volume"] = 6000
        expected = "resize"
    result = check(p, s, m)
    assert result["firedRule"] == rule, result
    assert result["verdict"] == expected, result
    assert result["rules"][:len(RULES)] == list(RULES)
    for item in result["checks"][:RULES.index(rule)]:
        assert item["result"] == "pass", result


def test_resizes_minimum_and_cash_fees(desk):
    p, s, m = desk
    p["qty"] = 240
    assert check(p, s, m)["qtyAfter"] == 80
    s.positions["AAA"] = position(qty=61)
    s.cash = 93900
    r = check(p, s, m)
    assert r["verdict"] == "veto" and r["firedRule"] == "per_name_cap"
    s.positions["AAA"]["qty"] = 80
    s.cash = 92000
    assert check(p, s, m)["qtyAfter"] == 0
    s.positions = {"USMV": position("core", qty=850)}
    s.cash = 15000
    assert check(p, s, m)["qtyAfter"] == 49
    p["qty"] = 19
    assert check(p, PortfolioState(cash=100000), m)["firedRule"] == "below_min_notional"


def test_invalidation_precedes_oversized_resize(desk):
    proposal, state, market = desk
    proposal["qty"] = 240
    assert check(proposal, state, market)["firedRule"] == "per_name_cap"
    state.stepUp["invalidated"] = True
    verdict = check(proposal, state, market)
    assert verdict["verdict"] == "veto"
    assert verdict["firedRule"] == "satellite_invalidated"
    assert verdict["qtyAfter"] == 0


def test_regime_cap_stepup_and_invalidation(desk):
    p, s, m = desk
    s.positions["BBB"] = position(qty=180)
    s.cash = 82000
    s.stepUp = dict(enabled=True, effectiveFrom="2026-11-18")
    assert check(p, s, m)["verdict"] == "approve"
    p["qty"] = 80
    assert check(p, s, m)["qtyAfter"] == 70
    m["sessionDate"] = "2026-11-18"
    assert check(p, s, m)["qtyAfter"] == 80
    m["bars"]["SPY"].iloc[-1] = [50, 51, 49, 50, 2_000_000]
    assert check(p, s, m)["qtyAfter"] == 20
    assert check(p, s, m)["firedRule"] == "regime"
    s.stepUp["invalidated"] = True
    assert check(p, s, m)["verdict"] == "veto"


def test_exits_bypass_every_entry_gate_but_duplicate(desk):
    p, s, m = desk
    s.positions["AAA"] = position(qty=50)
    p["side"] = "SELL"
    s.halted, s.dailyLossHalted, s.tier = True, True, "kill"
    s.ordersPlacedThisSession = 100
    assert check(p, s, {})["verdict"] == "approve"
    s.ticketedDecisionIds.append(p["decisionId"])
    assert check(p, s, {})["firedRule"] == "duplicate_decision"


def test_tiers_recovery_requires_full_session_and_kill_reason():
    s = PortfolioState(cash=100000, sessionDate="2026-11-17")
    events = update(s, 98000, "2026-11-17")
    assert s.tier == "reduced" and events[0]["type"] == "tier_changed"
    update(s, 99000, "2026-11-17", at_close=True)
    assert s.tier == "reduced"
    update(s, 99000, "2026-11-18")
    assert s.tier == "reduced"
    update(s, 99000, "2026-11-18", at_close=True)
    assert s.tier == "normal"
    update(s, 96000, "2026-11-18")
    assert s.tier == "exits_only"
    update(s, 97000, "2026-11-19", at_open=True)
    update(s, 97000, "2026-11-19", at_close=True)
    assert s.tier == "reduced"
    update(s, 94000, "2026-11-19")
    assert s.halted and s.tier == "kill"
    update(s, 101000, "2026-11-20", at_close=True)
    assert s.halted and s.tier == "kill"
    for reason in ("", "   ", None):
        with pytest.raises(ValueError): s.restart(reason)
    assert s.restart("Reviewed loss and reconciled all fills")["cleared"]
    assert not s.halted and s.tier == "exits_only"
    update(s, 101000, "2026-11-23", at_open=True)
    update(s, 101000, "2026-11-23", at_close=True)
    assert s.tier == "normal"


def test_daily_halt_latches_and_snapshot_start_is_preserved(desk):
    p, s, m = desk
    s.sessionDate = None
    events = update(s, 98500, "2026-11-17")
    assert s.dailyLossHalted and any(e["type"] == "halt" for e in events)
    update(s, 100000, "2026-11-17")
    assert check(p, s, m)["firedRule"] == "daily_loss"
    update(s, 100000, "2026-11-18", at_open=True)
    assert not s.dailyLossHalted


def test_fees():
    assert estimate_fees("BUY", 100) == .99
    assert estimate_fees("SELL", 100) == 1.0066
    assert estimate_fees("SELL", 100000) == 9.29
    result = realized_pnl(100, 100, 110)
    assert result["pnl"] == pytest.approx(1000-.99-1.0066)


def test_sizing_classification_halving_minimum_and_stops(desk):
    p, s, m = desk
    b = bars()
    b.loc[b.index[-1], "volume"] = 4_000_000
    quote = dict(last=float(b.close.iloc[-1]), ask=round(float(b.close.iloc[-1]), 2))
    rating = dict(ticker="AAA", decisionId=p["decisionId"], **{"class": "explained_up"}, confidence=1., tier="debate")
    normal = propose_entry(rating, b, quote, 100000)
    assert normal["status"] == "proposal", normal
    assert propose_entry(rating | dict(tier="single"), b, quote, 100000) == normal
    assert propose_entry(rating | dict(tier="single"), b, quote, 100000, "reduced") == propose_entry(rating, b, quote, 100000, "reduced")
    assert normal["signalAtr"] > 0 and normal["stop"] < normal["limitPrice"]
    quick = propose_entry(rating | dict(tier="quick"), b, quote, 100000)
    reduced = propose_entry(rating, b, quote, 100000, "reduced")
    assert quick["qty"] == reduced["qty"] == int(normal["sizing"]["proposedNotional"]*.5/normal["limitPrice"])
    assert quick["estFees"] == .99
    assert propose_entry(rating | dict(confidence=.1), b, quote, 100000)["reason"] == "below_min_notional"
    for classification in ("explained_down", "unexplained_up"):
        assert propose_entry(rating | {"class": classification}, b, quote, 100000)["status"] == "skip"
    b.loc[b.index[-1], "volume"] = 1_000_000
    assert propose_entry(rating, b, quote, 100000)["status"] == "skip"
    assert limit_price(dict(last=100)) == 100.10


def exit_bars(closes, start="2026-11-17"):
    return pd.DataFrame([dict(open=c, high=c+.2, low=c-.2, close=c, volume=1000000)
                         for c in closes], index=pd.bdate_range(start=start, periods=len(closes)))


def test_trail_never_loosens_and_stop_precedes_target():
    s = PortfolioState(cash=90000, positions={"AAA": position()})
    q = {"AAA": dict(last=104, bid=104)}
    b = exit_bars([102, 104, 103])
    result = propose_exits(s, {"AAA": b}, q, "2026-11-19", RUN)
    assert not result["proposals"]
    changes = result["updates"]["AAA"]
    assert changes["trailArmed"] and changes["stop"] == 101
    s.positions["AAA"].update(changes)
    result = propose_exits(s, {"AAA": exit_bars([102, 104, 103, 102])}, q, "2026-11-20", RUN)
    assert result["updates"]["AAA"]["stop"] == 101
    q["AAA"]["last"] = 100
    assert propose_exits(s, {"AAA": b}, q, "2026-11-20", RUN)["proposals"][0]["reason"] == "trailing stop"
    s.positions["AAA"] = position("bounce")
    b = exit_bars([100]); b.iloc[0] = [100, 121, 89, 100, 1000000]
    assert propose_exits(s, {"AAA": b}, q, "2026-11-17", RUN)["proposals"][0]["reason"] == "stop hit"
    b.iloc[0] = [100, 121, 99, 100, 1000000]
    assert propose_exits(s, {"AAA": b}, q, "2026-11-17", RUN)["proposals"][0]["reason"] == "bounce target"


@pytest.mark.parametrize("kind,horizon", [("drift", 5), ("bounce", 3)])
def test_time_exits_and_final_day_hold(kind, horizon):
    s = PortfolioState(cash=90000, positions={"AAA": position(kind)})
    q = {"AAA": dict(last=100, bid=100)}
    b = exit_bars([100]*horizon)
    assert not propose_exits(s, {"AAA": b.iloc[:-1]}, q, str(b.index[-2].date()), RUN)["proposals"]
    assert propose_exits(s, {"AAA": b}, q, str(b.index[-1].date()), RUN)["proposals"][0]["reason"] == "time exit"
    assert not propose_exits(s, {"AAA": b}, q, C.FINAL_DAY, RUN)["proposals"]
    s.tier = "kill"
    assert propose_exits(s, {}, q, C.FINAL_DAY, RUN)["proposals"][0]["reason"] == "kill liquidation"


def test_core_weights_band_and_risk_exemption(desk):
    p, s, m = desk
    target = weights(m["bars"])
    assert sum(target.values()) == pytest.approx(.5)
    assert len(propose_core(s, m["bars"], m["quotes"], m["prices"], RUN)) == 5
    ticker = C.CORE_ETFS[0]
    p.update(ticker=ticker, decisionId=f"{RUN}:{ticker}", sleeve="core", kind="core", qty=100)
    assert check(p, s, m)["verdict"] == "approve"
    s.positions = {t: position("core", qty=w*1000) for t, w in target.items()}
    s.cash = 50000
    assert propose_core(s, m["bars"], m["quotes"], m["prices"], RUN) == []
    removed = s.positions[ticker]["qty"]*.25
    s.positions[ticker]["qty"] -= removed
    s.cash += removed*100
    assert ticker in [p["ticker"] for p in propose_core(s, m["bars"], m["quotes"], m["prices"], RUN)]


@pytest.fixture
def ticket(desk):
    p, s, m = desk
    return OrderTicket.from_proposal(p, check(p, s, m), "a"*64, NOW)


def test_ticket_hash_and_adapter(ticket, monkeypatch):
    assert ticket.ticketHash == hashlib.sha256(canonical_bytes(ticket.body())).hexdigest()
    assert OrderTicket(**json.loads(json.dumps(ticket.to_dict()))).ticketHash == ticket.ticketHash
    monkeypatch.delenv("MOOMOO_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("MOOMOO_MARKET", raising=False)
    with pytest.raises(ValueError): to_sim_order(ticket, "123", 100)
    monkeypatch.setenv("MOOMOO_ACCOUNT_ID", "123")
    with pytest.raises(ValueError): to_sim_order(ticket)
    monkeypatch.setenv("MOOMOO_MARKET", "100")
    args = to_sim_order(ticket)
    assert args == dict(acc_id="123", market=100, symbol="US.AAA", order_type=1,
                        order_side=1, qty="50", price="100.00", order_trade_time_type=1, text=ticket.decisionId)
    assert verify_placed(ticket, args)["ok"]
    for key, value in dict(qty=51, price=101, order_side=2, symbol="US.BBB", acc_id="other").items():
        result = verify_placed(ticket, args | {key: value})
        assert not result["ok"] and result["mismatches"][key]["observed"] == value


@pytest.mark.parametrize("qty,outcome", [(0, "unfilled"), (20, "partial"), (50, "filled")])
def test_fill_reconciliation(ticket, qty, outcome):
    result = reconcile_fill(ticket, qty, 100 if qty else 0, "broker status")
    assert result["status"] == outcome and not result["cancel_leftover"]
    result = reconcile_fill(ticket, qty, 100 if qty else 0, "broker status", at_session_close=True)
    assert result["cancel_leftover"] == (qty < 50)
    assert result["fees"] == (.99 if qty else 0)
    with pytest.raises(ValueError): reconcile_fill(ticket, 51, 100, "filled")


def test_stepup_matched_calls_and_invalidation():
    rows = [dict(decisionId=str(i), llmExcess=.02, followExcess=.01) for i in range(15)]
    args = (rows, [], "2026-11-17", "2026-11-18")
    assert evaluate(*args, at_close=False)["decision"] == "defer_until_close"
    result = evaluate(*args, at_close=True)
    assert result["decision"] == "step_up_next_session" and result["state"]["effectiveFrom"] == "2026-11-18"
    trades = [r | dict(sleeve="satellite", fadeExcess=.03) for r in rows]
    result = evaluate(rows, trades, "2026-11-18", "2026-11-19", at_close=True, previous=result["state"])
    assert result["decision"] == "invalidate" and result["state"]["thesis"] == "failed"
    assert evaluate(*args, at_close=True, previous=result["state"])["decision"] == "invalidated"
    assert evaluate(rows[:-1], [], "2026-11-17", "2026-11-18", at_close=True)["decision"] == "unchanged"


def test_drills_are_shadow_only(desk, tmp_path):
    p, s, m = desk
    before = s.to_json()
    log = EventLog(tmp_path / f"{RUN}.jsonl")
    results = run_drills(p, s, m, log)
    assert len(results) == 5 and all(r["pass"] for r in results)
    assert s.to_json() == before
    events = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert all(e["type"] == "drill" and e["drill"] for e in events)
    assert verify(log.path).ok


def test_plan_session_real_cli_offline_and_replay(desk, tmp_path):
    p, s, m = desk
    s.cash = 98000
    s.positions["BBB"] = position(qty=20, stop=99)
    m["quotes"]["BBB"].update(last=98, bid=97.95, ask=98)
    m["bars"]["AAA"].loc[m["bars"]["AAA"].index[-1], "volume"] = 4_000_000
    m["quotes"]["AAA"].update(last=float(m["bars"]["AAA"].close.iloc[-1]),
                               ask=round(float(m["bars"]["AAA"].close.iloc[-1]), 2))
    m["quotes"]["AAA"]["bid"] = m["quotes"]["AAA"]["ask"]-.05
    payloads = dict(state=s.to_dict(), ratings=[dict(ticker="AAA", decisionId=f"{RUN}:AAA",
                    **{"class": "explained_up"}, confidence=1, tier="debate")],
                    bars={t: [dict(date=str(day.date()), **row.to_dict()) for day, row in f.iterrows()]
                          for t, f in m["bars"].items()},
                    quotes=dict(now=NOW, sessionDate="2026-11-17", regularOpen="2026-11-17T14:30:00Z",
                                regularClose="2026-11-17T21:00:00Z", quotes=m["quotes"]))
    for name, value in payloads.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    log = tmp_path / f"{RUN}.jsonl"
    command = [sys.executable, str(ROOT / "scripts/plan_session.py"), "--bars-asof", "2026-11-16",
               "--log", str(log), "--tickets-dir", str(tmp_path / "tickets")]
    for name in payloads: command += [f"--{name}", str(tmp_path / f"{name}.json")]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    output = tmp_path / "tickets" / f"{RUN}.json"
    manifest = json.loads(output.read_text())
    assert len(manifest["tickets"]) == 7, manifest
    assert manifest["tickets"][-1]["ticker"] == "AAA"
    assert manifest["tickets"][0]["side"] == "SELL"
    assert all(t["estFees"] == estimate_fees(t["side"], t["qty"]) for t in manifest["tickets"])
    state_after = json.loads((tmp_path / "state.json").read_text())
    assert state_after["positions"]["BBB"]["qty"] == 20 and state_after["cash"] == 98000
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(output.read_text())["tickets"] == manifest["tickets"]
    assert verify(log).ok


@pytest.mark.parametrize("gate", ["stale", "minutes", "spread", "correlation"])
def test_exact_risk_boundaries_are_allowed(desk, gate):
    p, s, m = desk
    if gate == "stale": m["quotes"]["AAA"]["ts"] = "2026-11-17T14:59:00Z"
    elif gate == "minutes": m["minutesSinceOpen"] = 5
    elif gate == "spread": m["quotes"]["AAA"].update(bid=99.925, ask=100.075)
    else:
        s.positions["BBB"] = position()
        # Orthogonal centered vectors make the sample correlation exactly 0.8.
        x = np.tile([-.001, .001, -.001, .001], 15)
        z = np.tile([-.001, -.001, .001, .001], 15)
        for ticker, r in [("AAA", x), ("BBB", .8*x+.6*z)]:
            f = m["bars"][ticker].iloc[-61:].copy()
            f["close"] = np.r_[100, 100*np.cumprod(1+r)]
            f["open"] = f.close
            f["low"], f["high"] = f.close-1, f.close+1
            m["bars"][ticker] = f
    assert check(p, s, m)["verdict"] == "approve"


def test_bounce_entry_gates_target_and_fixed_atr(desk):
    p, s, m = desk
    b = bars()
    previous = float(b.close.iloc[-2])
    close = previous*.999
    b.iloc[-1] = [close, close+1, close-1, close, 2_000_000]
    rating = dict(ticker="AAA", decisionId=p["decisionId"], **{"class": "unexplained_down"}, confidence=1, tier="debate")
    q = dict(ask=round(close, 2), last=close)
    result = propose_entry(rating, b, q, 100000)
    assert result["status"] == "proposal", result
    assert result["preDropClose"] == previous
    assert result["stop"] == max(result["limitPrice"]-C.K_bounce*result["signalAtr"],
                                  result["sizing"]["support"]-result["signalAtr"])
    b.loc[b.index[-1], "volume"] = 6_000_000
    assert propose_entry(rating, b, q, 100000)["status"] == "skip"
    b.iloc[-1] = [50, 51, 49, 50, 2_000_000]
    assert propose_entry(rating, b, dict(ask=50), 100000)["status"] == "skip"


def test_recovery_resets_when_band_is_breached():
    s = PortfolioState(cash=100000, tier="exits_only", sessionDate="2026-11-17")
    update(s, 97000, "2026-11-18", at_open=True)
    update(s, 96000, "2026-11-18")
    update(s, 97000, "2026-11-18", at_close=True)
    assert s.tier == "exits_only"
    update(s, 97000, "2026-11-19", at_close=True)
    assert s.tier == "reduced"


def test_missing_data_vetoes_and_first_trigger_wins(desk):
    p, s, m = desk
    del m["quotes"]["AAA"]["ts"]
    assert check(p, s, m)["firedRule"] == "stale_price"
    s.halted = True
    s.ticketedDecisionIds.append(p["decisionId"])
    result = check(p, s, m)
    assert result["firedRule"] == "kill_or_halted" and result["qtyAfter"] == 0


def test_pending_tickets_consume_entry_capacity(desk):
    p, s, m = desk
    ticket = OrderTicket.from_proposal(p, check(p, s, m), "a"*64, NOW)
    s.reserve(ticket)
    p["decisionId"] = "later:AAA"
    assert check(p, s, m)["qtyAfter"] == 30
    s.ordersPlacedThisSession = 29
    assert check(p, s, m)["firedRule"] == "max_orders"


def test_sell_reconciliation_and_fee_cap(ticket):
    sale = OrderTicket(**(ticket.body() | dict(side="SELL", qty=100000, estFees=9.29)))
    result = reconcile_fill(sale, 100000, 101, "FILLED", at_session_close=True)
    assert result["cashDelta"] == 10100000-9.29 and not result["cancel_leftover"]
    with pytest.raises(ValueError, match="limit price"):
        reconcile_fill(sale, 100, 99, "PARTIAL")


def test_live_and_history_stop_sequence_agree():
    from moowoo.history import simulate_trade
    f = exit_bars([100, 102, 104, 103, 100, 100], start="2026-11-16")
    context = dict(atr=2., support=None, target=120., score=0)
    historical = simulate_trade(f, f, f.index[0], context, "drift", k=3)
    entry = float(f.open.iloc[1])
    s = PortfolioState(cash=90000, positions={"AAA": position(entryPrice=entry,
                       highestClose=entry, stop=entry-6)})
    live = propose_exits(s, {"AAA": f}, {"AAA": dict(last=100, bid=100)}, "2026-11-23", RUN)
    assert historical["reason"] == "stop"
    assert live["proposals"][0]["reason"] == "stop hit"
    assert live["updates"]["AAA"]["stop"] == historical["stops"][-1]


def test_frozen_config_guard_accepts_only_authorized_addendum(monkeypatch):
    import plan_session
    frozen = plan_session.frozen_config()
    assert frozen["configHash"] == "9c1c03d43e142c29788b01947f3c4b6c2ea8206dd074b10c885bb905ae9ed6b4"
    monkeypatch.setattr(C, "PER_NAME_CAP", .09)
    with pytest.raises(ValueError, match="frozen configuration mismatch"):
        plan_session.frozen_config()
