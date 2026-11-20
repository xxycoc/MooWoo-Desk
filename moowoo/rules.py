"""Exact authorized non-strategy addenda; frozen strategy values remain unchanged."""

AUTONOMY_CHANGE = dict(
    type="rule_change", ruleId="AUTONOMY-01", date="2026-11-17",
    before="executor sim order tools always_ask (human approval per order)",
    after="executor sim order tools always_allow from the first session",
    reason="decided by Siang Woo: unattended operation; controls remain code risk desk, preflight guard, verify_placed halt, real-money tools disabled and no trade scope, drawdown tiers, daily loss halt and kill switch",
    effectiveFrom="first session", triggerDecisionIds=[])

PICKS_CHANGE = dict(
    type="rule_change", ruleId="PICKS-01", date="2026-11-18",
    before=dict(PICK_COUNT=15), after=dict(PICK_COUNT=5),
    reason="decided by Siang Woo: cut daily movers from 15 to 5 so a morning run fits its lease; every pick keeps the bull/bear/manager debate and a quick second opinion; before the first order",
    effectiveFrom="first session", triggerDecisionIds=[])

TOPOLOGY_CHANGE = dict(
    type="rule_change", ruleId="TOPOLOGY-01", date="2026-11-18",
    before="debate tier bull/bear/manager + quick second opinion",
    after="single researcher-rater tier sized as debate",
    reason="approved by Siang Woo 18 Nov: cut agents 7->3 to stop coordinator relay failures",
    effectiveFrom="first session after 18 Nov 05:00 SGT", triggerDecisionIds=[])

SIZING_CHANGE = dict(
    type="rule_change", ruleId="SIZING-01", date="2026-11-19",
    before=dict(CORE_WEIGHT=0.50, SATELLITE_CAP=0.25, SATELLITE_CAP_STEP_UP=0.40, PER_NAME_CAP=0.08,
                MAX_SPREAD=0.0015),
    after=dict(CORE_WEIGHT=0.30, SATELLITE_CAP=0.60, SATELLITE_CAP_STEP_UP=0.60, PER_NAME_CAP=0.20,
               MAX_SPREAD=0.005),
    reason="decided by Siang Woo 19 Nov: move capital from the defensive core to satellite trades for the remaining six sessions; stops, drawdown tiers, kill switch, regime cap, cash floor and long-only unchanged",
    effectiveFrom="first session after 19 Nov 01:00 SGT", triggerDecisionIds=[])

CORE_REBALANCE_CHANGE = dict(
    type="rule_change", ruleId="CORE-REBALANCE-01", date="2026-11-19",
    before=dict(CORE_REBALANCE_AFTER_FILLS=False),
    after=dict(CORE_REBALANCE_AFTER_FILLS=True),
    reason="requested by Siang Woo: size conditional core buys after planned core sells, but authorize only after full reconciled fills and post-sell core/cash checks; allocation limits unchanged",
    effectiveFrom="first session after matching prompt addendum and deployment", triggerDecisionIds=[])


REGIME_SIZING_CHANGE = dict(
    type="rule_change", ruleId="SIZING-02", date="2026-11-19",
    before=dict(REGIME_SATELLITE_CAP=0.20), after=dict(REGIME_SATELLITE_CAP=0.40),
    reason="decided by Siang Woo 19 Nov: in a weak regime allow satellites up to 40% of equity instead of 20% for the remaining sessions; all loss limits unchanged",
    effectiveFrom="first session after 20 Nov 00:00 SGT", triggerDecisionIds=[])

CORE_CASH_CHANGE = dict(
    type="rule_change", ruleId="CORE-REBALANCE-02", date="2026-11-19",
    before=dict(CORE_REBALANCE_CASH_FUNDED=False),
    after=dict(CORE_REBALANCE_CASH_FUNDED=True),
    reason="requested by Siang Woo 19 Nov: core buys funded by existing cash need not wait for core sells; cash floor and core limits unchanged",
    effectiveFrom="first session after 20 Nov 00:00 SGT", triggerDecisionIds=[])


BETA_CHANGE = dict(
    type="rule_change", ruleId="SLEEVE-01", date="2026-11-19",
    before=dict(BETA_ETF=None, BETA_WEIGHT=0),
    after=dict(BETA_ETF="SPY", BETA_WEIGHT=0.30),
    reason="decided by Siang Woo 19 Nov: hold 30% in SPY at all times so idle cash is invested; satellites use the room left above the 10% cash floor; loss limits unchanged",
    effectiveFrom="first session after 20 Nov 00:00 SGT", triggerDecisionIds=[])


FINAL_CLOSE_CHANGE = dict(
    type="rule_change", ruleId="FINAL-CLOSE-01", date="2026-11-20",
    before=dict(FINAL_LIQUIDATION_FROM=None, FINAL_STALE_PRICE_SECONDS=None),
    after=dict(FINAL_LIQUIDATION_FROM="12:00", FINAL_STALE_PRICE_SECONDS=300),
    reason="organiser clarification: only realised results count; no final-day buys; liquidate every sleeve from 12:00 New York before the 27 Nov 13:00 early close, retrying remaining quantities; final-liquidation sells accept quotes up to 300 s old",
    effectiveFrom="first session after 20 Nov 00:00 SGT", triggerDecisionIds=[])


LIMIT_BUFFER_CHANGE = dict(
    type="rule_change", ruleId="LIMIT-01", date="2026-11-20",
    before=dict(LIMIT_BUFFER=None), after=dict(LIMIT_BUFFER=0.005),
    reason="20 Nov morning: all eight approved tickets were skipped because quotes moved 0.1-0.8% between plan and dispatch; buy limits are set 0.5% above the ask and sell limits 0.5% below the bid, and dispatch only requires the fresh ask (buy) or bid (sell) to be within the limit",
    effectiveFrom="first session after 20 Nov 23:00 SGT", triggerDecisionIds=[])


TICKER_CAP_CHANGE = dict(
    type="rule_change", ruleId="TICKER-CAP-01", date="2026-11-20",
    before=dict(MAX_TICKER_VALUE=None), after=dict(MAX_TICKER_VALUE=40_000),
    reason="organiser clarification: cap each ticker at 40% of the USD 100000 start; shrink or drop buys using held and pending buy quantities at the ticket limit price",
    effectiveFrom="first session after 20 Nov 00:00 SGT", triggerDecisionIds=[])
