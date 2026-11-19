"""Offline, explicit-schema broker adapters and independent account books."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math
import os
import re

from . import broker_fields as fields
from .portfolio import PortfolioState, positive
from .input_files import InputFileError

EQUITY_MARK_TOLERANCE = 0.0025


def mapped(row, table):
    if not isinstance(row, dict):
        raise InputFileError("broker row must be an object")
    result = {}
    for target, source in table["required"].items():
        if source not in row or row[source] is None:
            raise InputFileError(f"missing required broker field: {source}")
        result[target] = row[source]
    for target, source in table["optional"].items():
        if source in row and row[source] is not None:
            result[target] = row[source]
    return result


def rows(payload, table):
    values = payload if table["rows"] is None else payload.get(table["rows"])
    if not isinstance(values, list):
        raise InputFileError("missing or invalid required broker rows list")
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
    if not isinstance(symbol, str):
        raise ValueError("unrecognized broker symbol")
    name = symbol.removeprefix(fields.SYMBOL_PREFIX)
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", name):
        raise ValueError("invalid broker ticker")
    return name


def parse_accounts(payload):
    # The live MCP tool wraps rows as {ret_code, ret_msg, data: {accounts: [...]}}.
    if isinstance(payload, dict) and "ret_code" in payload:
        payload = successful_data(payload).get("accounts")
    result = rows(payload, fields.ACCOUNT_LIST)
    for row in result:
        if type(row["accountType"]) is not int or type(row["market"]) is not int:
            raise InputFileError("account type and market must be integers")
        if type(row["accountId"]) not in (str, int):
            raise InputFileError("account ID must be a string or integer")
        row["accountId"] = str(row["accountId"])
        if not row["accountId"] or not isinstance(row["title"], str):
            raise InputFileError("invalid account identity")
    return result


def parse_cash(payload):
    if "ret_code" in payload:
        data = successful_data(payload)
        result = mapped(data, fields.CASH_INFO)
        for name in ("cash", "equity", "reserved"):
            result[name] = decimal_number(result[name], name, zero=True)
        for target, source in (("realizedProfit", "realized_profit"), ("unrealizedProfit", "unrealized_profit")):
            value = data.get(source)
            try:
                number = float(Decimal(str(value))) if value is not None else 0.0
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"invalid broker {source}") from exc
            if not math.isfinite(number):
                raise ValueError(f"invalid broker {source}")
            result[target] = number
    else:
        result = mapped(payload, dict(required=dict(cash="cash", equity="equity"),
                                      optional=dict(accountId="acc_id", market="market")))
    routing(result)
    for name in ("cash", "equity"):
        positive(result[name], name, zero=True)
    return result


def parse_positions(payload):
    data = successful_data(payload) if "ret_code" in payload else {"positions": payload.get("data")}
    result = rows(data, fields.POSITION_LIST)
    seen = set()
    for row in result:
        routing(row)
        row["ticker"] = ticker(row["ticker"])
        if row["ticker"] in seen:
            raise ValueError("duplicate broker position")
        seen.add(row["ticker"])
        for name in ("qty", "avgCost", "marketPrice"):
            row[name] = decimal_number(row[name], name, zero=name == "qty", whole=name == "qty")
    return result


def successful_data(payload):
    if not isinstance(payload, dict) or type(payload.get("ret_code")) is not int:
        raise InputFileError("missing required broker field: ret_code")
    if not isinstance(payload.get("ret_msg"), str):
        raise InputFileError("missing required broker field: ret_msg")
    if payload["ret_code"] != 0:
        raise ValueError(f"broker ret_code {payload['ret_code']}: {payload['ret_msg']}")
    if not isinstance(payload.get("data"), dict):
        raise InputFileError("missing required broker field: data")
    return payload["data"]


def decimal_number(value, name, *, zero=False, whole=False):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputFileError(f"invalid broker decimal: {name}") from exc
    if not number.is_finite() or number < 0 or (not zero and number == 0):
        raise InputFileError(f"invalid broker decimal: {name}")
    if whole and number != number.to_integral_value():
        raise InputFileError(f"broker {name} requires whole shares")
    converted = int(number) if whole else float(number)
    positive(converted, name, zero=zero)
    return converted


def parse_history(payload, fetch_page=None):
    result, cursors = [], set()
    while True:
        data = successful_data(payload)
        result.extend(rows(data, fields.ORDER_HISTORY))
        pagination = data.get("pagination", payload.get("pagination"))
        if "pagination" in data and "pagination" in payload and data["pagination"] != payload["pagination"]:
            raise ValueError("conflicting broker pagination")
        if (not isinstance(pagination, dict) or type(pagination.get("has_more")) is not bool
                or not isinstance(pagination.get("next_key"), str)):
            raise InputFileError("missing required broker pagination fields")
        if not pagination["has_more"]:
            break
        cursor = pagination["next_key"]
        if not cursor or cursor in cursors:
            raise ValueError("invalid or repeated history cursor")
        if fetch_page is None:
            raise ValueError("history incomplete: collect all pages before reconciliation")
        cursors.add(cursor)
        payload = fetch_page(cursor)
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
        if type(row["status"]) is not int:
            raise InputFileError("broker status must be an integer")
        row["statusLabel"] = fields.ORDER_STATUS_LABELS_PROVISIONAL.get(row["status"], "unknown (provisional)")
        for name in ("qty", "limitPrice", "filledQty", "avgPrice"):
            row[name] = decimal_number(row[name], name, zero=name in ("filledQty", "avgPrice"),
                                       whole=name in ("qty", "filledQty"))
        if row["filledQty"] > row["qty"] or (row["filledQty"] and not row["avgPrice"]):
            raise ValueError("inconsistent broker fill quantities")
        row["fillState"] = "filled" if row["filledQty"] == row["qty"] else "partial" if row["filledQty"] else "unfilled"
        row["terminal"] = row["fillState"] == "filled"
        for name in ("createTime", "updateTime"):
            if name in row:
                if not isinstance(row[name], str) or not row[name].isdigit():
                    raise InputFileError("broker timestamps must be microsecond strings")
                row[name] = int(row[name])
    return result


def parse_placement(payload):
    result = mapped(successful_data(payload), fields.INPUT_ORDER)
    if not isinstance(result["orderId"], str) or not result["orderId"].strip():
        raise ValueError("placement orderId must be nonempty")
    return result


def snapshot_to_state(positions, cash, previous, *, decisions=None):
    """Broker owns quantities/cost/cash; ticker AND identity guard strategy carryover.

    If position text is absent, the caller must supply history-backed identities.
    """
    snapshot = previous.to_dict()
    snapshot.update(cash=cash["cash"], brokerReserved=cash.get("reserved", 0), positions={})
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
    marks = {row["ticker"]: row["marketPrice"] for row in positions}
    equity = state.equity(marks)
    # Cash and positions are separate broker calls, so live marks move between them (18 Nov:
    # USD 9.75 on USD 34k). Quantities and cash come from the broker exactly; allow 0.25% of marks.
    held = sum(row["qty"] * row["marketPrice"] for row in positions)
    tolerance = max(1, EQUITY_MARK_TOLERANCE * held)
    if abs(equity-cash["equity"]) > tolerance:
        raise ValueError(f"broker cash/position equity differs by more than USD {tolerance:.2f}")
    return state
