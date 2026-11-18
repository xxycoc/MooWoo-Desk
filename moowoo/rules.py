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
