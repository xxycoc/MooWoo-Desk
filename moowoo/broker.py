"""Offline, explicit-schema broker adapters and independent account books."""

from copy import deepcopy
import os
import re

from . import broker_fields as fields
from .portfolio import PortfolioState, positive


def mapped(row, table):
    if not isinstance(row, dict):
        raise ValueError("broker row must be an object")
    result = {}
    for target, source in table["required"].items():
        if source not in row or row[source] is None:
            raise ValueError(f"missing required broker field: {source}")
        result[target] = row[source]
    for target, source in table["optional"].items():
        if source in row and row[source] is not None:
            result[target] = row[source]
    return result


def rows(payload, table):
    values = payload if table["rows"] is None else payload[table["rows"]]
    if not isinstance(values, list):
        raise ValueError("broker rows must be a list; envelope mapping is provisional")
    return [mapped(row, table) for row in values]


def account_context():
    account = os.environ.get("MOOMOO_ACCOUNT_ID", "")
    market = os.environ.get("MOOMOO_MARKET", "")
    if not account.strip() or not market.isdigit() or int(market) != 100:
        raise ValueError("MOOMOO_ACCOUNT_ID and US MOOMOO_MARKET=100 required")
    return account, int(market)


def routing(row):
    account, market = account_context()
    if "accountId" in row and str(row["accountId"]) != account:
        raise ValueError("broker account mismatch")
    if "market" in row and (type(row["market"]) is not int or row["market"] != market):
        raise ValueError("broker market mismatch")


def ticker(symbol):
    if not isinstance(symbol, str) or not symbol.startswith(fields.SYMBOL_PREFIX):
        raise ValueError("unrecognized broker symbol")
    name = symbol[len(fields.SYMBOL_PREFIX):]
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", name):
        raise ValueError("invalid broker ticker")
    return name


def parse_accounts(payload):
    result = rows(payload, fields.ACCOUNT_LIST)
    for row in result:
        if type(row["accountType"]) is not int or type(row["market"]) is not int:
            raise ValueError("account type and market must be integers")
        if type(row["accountId"]) not in (str, int):
            raise ValueError("account ID must be a string or integer")
        row["accountId"] = str(row["accountId"])
        if not row["accountId"] or not isinstance(row["title"], str):
            raise ValueError("invalid account identity")
    return result


def parse_cash(payload):
    result = mapped(payload, fields.CASH_INFO)
    routing(result)
    for name in ("cash", "equity"):
        positive(result[name], name, zero=True)
    return result


def parse_positions(payload):
    result = rows(payload, fields.POSITION_LIST)
    seen = set()
    for row in result:
        routing(row)
        row["ticker"] = ticker(row["ticker"])
        if row["ticker"] in seen:
            raise ValueError("duplicate broker position")
        seen.add(row["ticker"])
        for name in ("qty", "avgCost", "marketPrice"):
            positive(row[name], name, zero=name == "qty")
    return result


def parse_history(payload):
    if payload.get(fields.ORDER_HISTORY["nextKey"]):
        raise ValueError("history incomplete: collect all pages before reconciliation")
    result = rows(payload, fields.ORDER_HISTORY)
    seen = set()
    for row in result:
        routing(row)
        row["ticker"] = ticker(row["ticker"])
        if not isinstance(row["orderId"], str) or not row["orderId"] or row["orderId"] in seen:
            raise ValueError("missing or duplicate order ID")
        seen.add(row["orderId"])
        if not isinstance(row["decisionId"], str) or not row["decisionId"]:
            raise ValueError("missing order decisionId")
        if type(row["side"]) is not int or row["side"] not in fields.ORDER_SIDES:
            raise ValueError("unrecognized order side")
        row["side"] = fields.ORDER_SIDES[row["side"]]
        if row["status"] not in fields.ORDER_STATUSES:
            raise ValueError("unrecognized broker order status")
        row["terminal"] = fields.ORDER_STATUSES[row["status"]] != "open"
        for name in ("qty", "limitPrice", "filledQty", "avgPrice"):
            positive(row[name], name, zero=name in ("filledQty", "avgPrice"))
        if row["filledQty"] > row["qty"] or (row["status"] == "FILLED" and row["filledQty"] != row["qty"]):
            raise ValueError("inconsistent broker fill quantities")
    return result


def parse_placement(payload):
    result = mapped(payload, fields.INPUT_ORDER)
    if not isinstance(result["orderId"], str) or not result["orderId"].strip():
        raise ValueError("placement orderId must be nonempty")
    if result.get("status", "SUBMITTED") not in ("SUBMITTED", "PARTIAL", "FILLED"):
        raise ValueError("placement was not accepted")
    return result


def snapshot_to_state(positions, cash, previous, *, decisions=None):
    """Broker owns quantities/cost/cash; ticker AND identity guard strategy carryover.

    If position text is absent, the caller must supply history-backed identities.
    """
    snapshot = previous.to_dict()
    snapshot.update(cash=cash["cash"], positions={})
    decisions = decisions or {}
    for row in positions:
        if not row["qty"]:
            continue
        name = row["ticker"]
        prior = previous.positions.get(name)
        identity = row.get("decisionId") or decisions.get(name)
        if not prior or not identity or prior.get("decisionId") != identity:
            raise ValueError(f"unmatched strategy identity: {name}")
        position = deepcopy(prior)
        position.update(qty=row["qty"], avgCost=row["avgCost"])
        snapshot["positions"][name] = position
    state = PortfolioState.from_dict(snapshot)
    equity = state.equity({row["ticker"]: row["marketPrice"] for row in positions})
    if abs(equity-cash["equity"]) > 1:
        raise ValueError("broker cash/position equity differs by more than USD 1")
    return state
