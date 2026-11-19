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
