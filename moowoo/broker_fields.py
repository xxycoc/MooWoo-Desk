"""One mapping per tool. Account row names are confirmed; ALL others provisional.

Envelopes and status vocabulary also need captured MCP responses. No aliases or
heuristic fallback: correct these tables against reviewed real responses.
"""

ACCOUNT_LIST = dict(rows=None, required=dict(accountId="account_id", market="market_id",
    accountType="account_type", title="account_title"), optional=dict(brokerId="broker_id",
    intraAccountId="intra_account_id"))
CASH_INFO = dict(rows=None, required=dict(cash="cash", equity="equity"),
                 optional=dict(accountId="acc_id", market="market"))
POSITION_LIST = dict(rows="data", required=dict(ticker="symbol", qty="qty", avgCost="avg_cost",
    marketPrice="market_price"), optional=dict(decisionId="text", accountId="acc_id", market="market"))
ORDER_HISTORY = dict(rows="data", required=dict(orderId="order_id", ticker="symbol",
    decisionId="text", side="order_side", qty="qty", limitPrice="price", filledQty="filled_qty",
    avgPrice="avg_price", status="status"), optional=dict(accountId="acc_id", market="market"),
    nextKey="next_key")
INPUT_ORDER = dict(rows=None, required=dict(orderId="order_id"),
                   optional=dict(status="status", reason="reason", args="args"))
ORDER_STATUSES = {"SUBMITTED": "open", "PARTIAL": "open", "FILLED": "filled",
                  "CANCELLED": "cancelled", "REJECTED": "rejected"}
SYMBOL_PREFIX = "US."
ORDER_SIDES = {1: "BUY", 2: "SELL"}
