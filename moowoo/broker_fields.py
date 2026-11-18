"""Explicit tool mappings; evidence and remaining assumptions: docs/execution.md."""

ACCOUNT_LIST = dict(rows=None, required=dict(accountId="account_id", market="market_id",
    accountType="account_type", title="account_title"), optional=dict(brokerId="broker_id",
    intraAccountId="intra_account_id"))
CASH_INFO = dict(rows=None, required=dict(cash="balance", equity="total_asset", reserved="hold"),
                 optional=dict(accountId="acc_id", market="market"))
POSITION_LIST = dict(rows="positions", required=dict(ticker="symbol", qty="qty", avgCost="cost_price",
    marketPrice="cur_price"), optional=dict(decisionId="text", accountId="acc_id", market="market"))
ORDER_HISTORY = dict(rows="orders", required=dict(orderId="order_id", ticker="symbol",
    decisionId="text", side="side", qty="qty", limitPrice="price", filledQty="cum_qty",
    avgPrice="avg_fill_price", status="status"), optional=dict(accountId="acc_id",
    internalMarket="market", createTime="create_time", updateTime="update_time",
    timeInForce="time_in_force", sessionType="order_trade_time_type", orderType="order_type"))
INPUT_ORDER = dict(rows=None, required=dict(orderId="order_id"),
                   optional=dict(status="status", reason="reason", args="args"))
ORDER_STATUS_LABELS_PROVISIONAL = {2: "accepted/resting (observed)", 5: "cancelled (observed)"}
SYMBOL_PREFIX = "US."
ORDER_SIDES = {1: "BUY", 2: "SELL"}
