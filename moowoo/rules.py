"""Exact authorized non-strategy addenda; frozen strategy values remain unchanged."""

AUTONOMY_CHANGE = dict(
    type="rule_change", ruleId="AUTONOMY-01", date="2026-11-17",
    before="executor sim order tools always_ask (human approval per order)",
    after="executor sim order tools always_allow from the first session",
    reason="decided by Siang Woo: unattended operation; controls remain code risk desk, preflight guard, verify_placed halt, real-money tools disabled and no trade scope, drawdown tiers, daily loss halt and kill switch",
    effectiveFrom="first session", triggerDecisionIds=[])
